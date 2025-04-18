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
import os

def filter_npz_by_filenames(npz_path, txt_path, output_path):
    
    data_list = np.load(npz_path, allow_pickle=True)['arr_0']
   
    with open(txt_path, 'r') as f:
        exclude_filenames = set(line.strip() for line in f if line.strip())

    # Filter the data list
    filtered_data = []
    excluded_count = 0
    
    for item in data_list:
            
        filename = item['uuid']
        
        if filename in exclude_filenames:
            excluded_count += 1
            print(filename)
        else:
            filtered_data.append(item)
    
    # Save the filtered data
    kept_count = len(filtered_data)
    total_count = len(data_list)
    print(f"Original items: {total_count}")
    print(f"Kept items: {kept_count}")
    print(f"Removed items: {excluded_count}")
    
    print(f"Saving filtered data")
    np.savez_compressed(output_path, filtered_data, allow_pickle=True) 

def main():
    issue_list = "data_utils/issue_data_list.txt"  # Change this to your text file path
    npz_path_train = "articulation_xlv2_train.npz"  # Change this to your NPZ file path
    output_path_train = "articulation_xlv2_train_update.npz"
    npz_path_test = "articulation_xlv2_test.npz"  # Change this to your NPZ file path
    output_path_test = "articulation_xlv2_test_update.npz"
    
    filter_npz_by_filenames(npz_path_train, issue_list, output_path_train)
    filter_npz_by_filenames(npz_path_test, issue_list, output_path_test)
        
if __name__ == "__main__":
    main()