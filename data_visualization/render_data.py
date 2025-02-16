import os
import numpy as np
import cv2

from pyrender_wrapper import PyRenderWrapper
from data_loader import DataLoader

def main():
    loader = DataLoader()
    
    raw_size = (960, 960)
    renderer = PyRenderWrapper(raw_size)
    
    output_dir = 'render_results'
    os.makedirs(output_dir, exist_ok=True)
    
    rig_path = 'examples/0a59c5ffa4a1476bac6d540b79947f31.txt'
    mesh_path = rig_path.replace('.txt', '.obj')
    
    filename = os.path.splitext(os.path.basename(rig_path))[0]

    loader.load_rig_data(rig_path)
    loader.load_files(mesh_path)
    input_dict = loader.query_mesh_rig()

    angles = [0, np.pi/2, np.pi, 3*np.pi/2] 
    
    bbox_center = loader.mesh.bounding_box.centroid
    bbox_size = loader.mesh.bounding_box.extents
    distance = np.max(bbox_size) * 2
    
    subfolder_path = os.path.join(output_dir, filename)
    
    os.makedirs(subfolder_path, exist_ok=True)
    
    for i, angle in enumerate(angles):
        print(f"Rendering view at {np.degrees(angle)} degrees")
        
        renderer.set_camera_view(angle, bbox_center, distance)
        renderer.align_light_to_camera()

        color = renderer.render(input_dict)[0]
        
        output_filename = f"{filename}_view{i+1}.png"
        output_filepath = os.path.join(subfolder_path, output_filename)
        cv2.imwrite(output_filepath, color)
if __name__ == "__main__":
    main()