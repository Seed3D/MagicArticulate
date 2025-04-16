from huggingface_hub import hf_hub_download

file_path = hf_hub_download(
    repo_id="Maikou/Michelangelo",
    filename="checkpoints/aligned_shape_latents/shapevae-256.ckpt",
    local_dir="third_party/Michelangelo"
)

file_path = hf_hub_download(
    repo_id="Seed3D/MagicArticulate",
    filename="skeleton_ckpt/checkpoint_trainonv2_hier.pth",
    local_dir=""
)

file_path = hf_hub_download(
    repo_id="Seed3D/MagicArticulate",
    filename="skeleton_ckpt/checkpoint_trainonv2_spatial.pth",
    local_dir=""
)