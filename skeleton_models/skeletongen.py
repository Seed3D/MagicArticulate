#  Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# 
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
# 
#  http://www.apache.org/licenses/LICENSE-2.0
# 
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
import torch
from torch import nn
from transformers import AutoModelForCausalLM
from third_party.Michelangelo.encode import load_model
from skeleton_models.shape_opt import ShapeOPTConfig

def undiscretize(t, low, high, num_discrete):
    assert (t >= 0).all() and (t <= num_discrete-1).all()
    assert high > low
    t = t.float()
    t /= num_discrete
    t = t * (high - low) + low
    assert (t < high).all() and (t >= low).all()
    return t

class SkeletonGPT(nn.Module):
    def __init__(self, args):
        super().__init__()

        self.args = args
        self.point_encoder = load_model()
      
        self.cond_length = 257
        self.cond_dim = 768
    
        self.n_discrete_size = args.n_discrete_size

        self.bone_per_token = 6  # (2 joints per bone)
        self.max_length = int(args.n_max_bones * self.bone_per_token + 2 + self.cond_length)
        self.pad_id = -1
        
        self.coor_continuous_range = (-0.5, 0.5)

        vocab_size = self.n_discrete_size + 3 # 3 for bos, eos, pad
        self.config = ShapeOPTConfig.from_pretrained(
            args.llm,
            n_positions=self.max_length,
            max_position_embeddings=self.max_length,
            vocab_size = vocab_size,
            _attn_implementation="flash_attention_2"
        )

        self.bos_token_id = 0
        self.eos_token_id = 1
        self.pad_token_id = 2

        self.config.bos_token_id = self.bos_token_id
        self.config.eos_token_id = self.eos_token_id
        self.config.pad_token_id = self.pad_token_id
        self.config._attn_implementation ="flash_attention_2"
        self.config.n_discrete_size = self.n_discrete_size
        self.config.bone_per_token = self.bone_per_token
        self.config.cond_length = self.cond_length

        self.config.word_embed_proj_dim = self.config.hidden_size # 1024
        
       
        self.transformer = AutoModelForCausalLM.from_config(
            config=self.config, attn_implementation="flash_attention_2")
        
        self.cond_head_proj = nn.Linear(self.cond_dim, self.config.word_embed_proj_dim)
        self.cond_proj = nn.Linear(self.cond_dim, self.config.word_embed_proj_dim)

        self.eval()

    def detokenize(self, input_ids):
        # input_ids: torch.Tensor of shape (batch_size, seq_length)
        batch_size = input_ids.size(0)

        continuous_coors_list = []
        num_bones_list = []
        
        for i in range(batch_size):
            cur_ids = input_ids[i]  # Shape: (seq_length,)

            # Remove padding tokens
            cur_ids = cur_ids[cur_ids != self.pad_id]  # Shape: (effective_seq_length,)
        
            # Check if length is a multiple of 6 (2 joints * 3 coordinates)
            if cur_ids.numel() % 6 != 0:
                return None
                # raise ValueError(f"Invalid length of input_ids in sample {i}. It should be a multiple of 6.")

            num_bones = cur_ids.numel() // 6
            num_bones_list.append(num_bones)

            # Reshape into (num_bones, 6)
            bone_coords = cur_ids.view(num_bones, 6)  # Shape: (num_bones, 6)

            # Undiscretize the coordinates
            # Initialize tensor to hold bone coordinates
            bones_coors = torch.zeros((num_bones, 2, 3), dtype=torch.float16, device=cur_ids.device)

            for j in range(num_bones):
                bone_coord = bone_coords[j]  # Shape: (6,)

                # Split into two joints
                joint1_ids = bone_coord[:3]
                joint2_ids = bone_coord[3:]

                # Undiscretize joint coordinates
                joint1_coords = undiscretize(joint1_ids, self.coor_continuous_range[0], self.coor_continuous_range[1], self.n_discrete_size)
                joint2_coords = undiscretize(joint2_ids, self.coor_continuous_range[0], self.coor_continuous_range[1], self.n_discrete_size)

                # Assign to bones_coors
                bones_coors[j, 0, :] = joint1_coords
                bones_coors[j, 1, :] = joint2_coords

            continuous_coors_list.append(bones_coors)
        
        max_num_bones = max(num_bones_list)

        # Initialize the continuous_coors tensor with NaNs
        continuous_coors = torch.full(
            (batch_size, max_num_bones, 2, 3),
            float('nan'),
            dtype=torch.float16,
            device=input_ids.device
        )

        # Place the bones_coors into continuous_coors
        for i in range(batch_size):
            num_bones = num_bones_list[i]
            continuous_coors[i, :num_bones, :, :] = continuous_coors_list[i]

        return continuous_coors  # Shape: (batch_size, max_num_bones, 2, 3)


    # def forward(self, data_dict: dict, is_eval: bool = False) -> dict:
    #     return self.generate(data_dict)

    def process_point_feature(self, point_feature):
        
        encode_feature = torch.zeros(self.args.batchsize_per_gpu, self.cond_length, self.config.word_embed_proj_dim,
                                    device=self.cond_head_proj.weight.device, dtype=self.cond_head_proj.weight.dtype)
        encode_feature[:, 0] = self.cond_head_proj(point_feature[:, 0])
        shape_latents = self.point_encoder.to_shape_latents(point_feature[:, 1:])

        encode_feature[:, 1:] = self.cond_proj(shape_latents)
        
        return encode_feature

    @torch.no_grad()
    def generate(self, data_dict) -> dict:

        point_feature = self.point_encoder.encode_latents(data_dict["pc_normal"])
        processed_point_feature = self.process_point_feature(point_feature=point_feature)
        generate_length = self.max_length - self.cond_length
        net_device = next(self.parameters()).device
        outputs = torch.ones(self.args.batchsize_per_gpu, generate_length).long().to(net_device) * self.eos_token_id
        # batch x ntokens
        if self.args.num_beams is not None and "pc_normal" in data_dict:
            results = self.transformer.generate(
                inputs_embeds=processed_point_feature,
                max_new_tokens=generate_length,  # all faces plus two
                num_beams=self.args.num_beams,
                bos_token_id=self.bos_token_id,
                eos_token_id=self.eos_token_id,
                pad_token_id=self.pad_token_id,
            )
        else:
            results = self.transformer.generate(
                inputs_embeds = processed_point_feature,
                max_new_tokens = generate_length, # all faces plus two
                do_sample=True,
                top_k=50,
                top_p=0.95,
                bos_token_id = self.bos_token_id,
                eos_token_id = self.eos_token_id,
                pad_token_id = self.pad_token_id,
            )
        assert results.shape[1] <= generate_length # B x ID  bos is not included since it's predicted
        outputs[:, :results.shape[1]] = results
        # batch x ntokens ====> batch x ntokens x D
        outputs = outputs[:, 1: -1] # eos and bos removed

        outputs[outputs == self.bos_token_id] = self.pad_id
        outputs[outputs == self.eos_token_id] = self.pad_id
        outputs[outputs == self.pad_token_id] = self.pad_id

        outputs[outputs != self.pad_id] -= 3
        
        gen_joints = self.detokenize(outputs)

        return gen_joints