CUDA_VISIBLE_DEVICES=0 python evaluate.py --dataset_path articulation_xlv2_test.npz \
            --pretrained_weights checkpoints \
            --save_name infer_results_xl --input_pc_num 8192 \
            --save_render --hier_order

# remove --hier_order if model is trained using spatial order
# when evaluate on xl2.0-test, it needs time as we have 2000 data to inference.