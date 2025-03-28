from huggingface_hub import hf_hub_download

file_path = hf_hub_download(
    repo_id="Maikou/Michelangelo",
    filename="checkpoints/aligned_shape_latents/shapevae-256.ckpt",
    local_dir="third_party/Michelangelo"
)