CUDA_VISIBLE_DEVICES=0 python demo.py --input_dir ./meshes \
            --pretrained_weights checkpoints \
            --save_name infer_results_demo_spatial --input_pc_num 8192 \
            --save_render --apply_marching_cubes

# CUDA_VISIBLE_DEVICES=0 python demo.py --input_dir ./meshes \
#             --pretrained_weights checkpoints \
#             --save_name infer_results_demo_hier --input_pc_num 8192 \
#             --save_render --apply_marching_cubes --hier_order