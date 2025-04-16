CUDA_VISIBLE_DEVICES=0 python demo.py --input_dir ./examples \
            --pretrained_weights skeleton_ckpt/ckpt_trainonv2_hier.pth \
            --save_name infer_results_demo_hier --input_pc_num 8192 \
            --save_render --apply_marching_cubes --hier_order