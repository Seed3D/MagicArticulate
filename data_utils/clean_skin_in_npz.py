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
import numpy as np
import scipy.sparse as sp
import os

def check_and_clean_skinning_weights(file_path, output_path, tolerance=0.1):
    """
    Check if all rows in pc_skinning_weights sum to 1 for each item in the NPZ file.
    Remove invalid items and save a cleaned version.
    
    Args:
        file_path: Path to the input NPZ file
        output_path: Path for the cleaned NPZ file
        tolerance: Tolerance for floating point comparison
        
    Returns:
        tuple: (cleaned_data_list, removed_indices)
    """
    data_list = np.load(file_path, allow_pickle=True)['arr_0']
    
    invalid_indices = []
    valid_data_list = []
    
    for idx, data in enumerate(data_list):
        is_valid = True

        weights_data = data['skinning_weights_value']
        weights_row = data['skinning_weights_row']
        weights_col = data['skinning_weights_col']
        weights_shape = data['skinning_weights_shape']
            
        skinning_sparse = sp.coo_matrix(
            (weights_data, (weights_row, weights_col)), 
            shape=weights_shape
        )
        
        skinning_csr = skinning_sparse.tocsr()
        row_sums = np.array(skinning_csr.sum(axis=1)).flatten()

        invalid_rows = np.where(np.abs(row_sums - 1.0) > tolerance)[0]
        
        if len(invalid_rows) > 0:
            min_sum = np.min(row_sums)
            max_sum = np.max(row_sums)
            invalid_indices.append((data['uuid'], f"{len(invalid_rows)} rows, range: [{min_sum:.6f}, {max_sum:.6f}]"))
            is_valid = False
    
        if is_valid:
            valid_data_list.append(data)
    
    # Save the cleaned data
    if valid_data_list:
        np.savez_compressed(output_path, valid_data_list, allow_pickle=True) 
        print(f"Saved {len(valid_data_list)} valid items to {output_path}")

    return valid_data_list, invalid_indices

def main():
    # File paths
    file_path = "articulation_xlv2_train.npz"  # "articulation_xlv2_test.npz"
    log_file = "invalid_skinning_weights_intrain.txt" # "invalid_skinning_weights_intest.txt"
    output_path = "articulation_xlv2_train_updated.npz"  # "articulation_xlv2_test_updated.npz"

    # Clean the data
    valid_data, invalid_indices = check_and_clean_skinning_weights(file_path, output_path)
    
    # Log the results
    with open(log_file, "w") as f:
        f.write(f"Original file: {file_path}\n")
        f.write(f"Cleaned file: {output_path}\n")
        f.write(f"Total items: {len(np.load(file_path, allow_pickle=True)['arr_0'])}\n")
        f.write(f"Valid items: {len(valid_data)}\n")
        f.write(f"Removed items: {len(invalid_indices)}\n\n")
        
        if invalid_indices:
            f.write("Details of removed items:\n")
            for idx, details in invalid_indices:
                f.write(f"  Index {idx}: {details}\n")
    
    print(f"Cleaning complete. Results written to {log_file}")

if __name__ == "__main__":
    main()