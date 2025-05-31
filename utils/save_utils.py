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
import os
import numpy as np
import cv2
import json
import trimesh

from collections import deque, defaultdict
from scipy.cluster.hierarchy import linkage, fcluster

from data_utils.pyrender_wrapper import PyRenderWrapper
from data_utils.data_loader import DataLoader

def save_mesh(vertices, faces, filename):

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)    
    mesh.export(filename, file_type='obj')

def pred_joints_and_bones(bone_coor):
    """
    get joints (j,3) and bones (b,2) from (b,2,3), preserve the parent-child relationship
    """
    parent_coords = bone_coor[:, 0, :]  # (b, 3)
    child_coords = bone_coor[:, 1, :]   # (b, 3)

    all_coords = np.vstack([parent_coords, child_coords])  # (2b, 3)
    pred_joints, indices = np.unique(all_coords, axis=0, return_inverse=True)

    b = bone_coor.shape[0]
    parent_indices = indices[:b]
    child_indices = indices[b:]

    pred_bones = np.column_stack([parent_indices, child_indices])
    
    return pred_joints, pred_bones

def remove_duplicate_joints(joints, bones, root_index=None):

    coord_to_indices = {}
    for idx, coord in enumerate(joints):
        key = tuple(coord) 
        coord_to_indices.setdefault(key, []).append(idx)

    representative = {}  # old_index -> rep_index
    for coord, idx_list in coord_to_indices.items():
        rep = idx_list[0] 
        for idx in idx_list:
            representative[idx] = rep

    remapped_bones_set = set() 
    for parent_old, child_old in bones:
        p_rep = representative[parent_old]
        c_rep = representative[child_old]
        # remove self connected bones
        if p_rep != c_rep:
            remapped_bones_set.add((p_rep, c_rep))

    remapped_bones = list(remapped_bones_set)

    used_indices = set()
    for p_rep, c_rep in remapped_bones:
        used_indices.add(p_rep)
        used_indices.add(c_rep)
    
    if root_index is not None:
        root_rep = representative[root_index]
        used_indices.add(root_rep)

    used_indices = sorted(used_indices)

    # old index --> new index
    old_to_new = {}
    for new_idx, old_idx in enumerate(used_indices):
        old_to_new[old_idx] = new_idx

    # get new joints
    new_joints = np.array([joints[old_idx] for old_idx in used_indices], dtype=joints.dtype)

    # get new bones
    new_bones = []
    for p_rep, c_rep in remapped_bones:
        p_new = old_to_new[p_rep]
        c_new = old_to_new[c_rep]
        new_bones.append((p_new, c_new))
    if root_index is not None:
        new_root_index = old_to_new[root_rep]
    new_bones = np.array(new_bones, dtype=int)
    
    if root_index is not None:
        return new_joints, new_bones, new_root_index
    else:
        return new_joints, new_bones


def save_skeleton_to_txt(pred_joints, pred_bones, pred_root_index, hier_order, vertices, filename='skeleton.txt'):
    """
    save skeleton to txt file, the format follows Rignet (joints, root, hier)
    
    if hier_order: the first joint index in bone is root joint index, and parent-child relationship is established in bones.
    else: we set the joint nearest to the mesh center as the root joint, and then build hierarchy starting from root.
    """
    
    num_joints = pred_joints.shape[0]
    
    # assign joint names
    joint_names = [f'joint{i}' for i in range(num_joints)]
    
    adjacency = defaultdict(list)
    for bone in pred_bones:
        idx_a, idx_b = bone
        adjacency[idx_a].append(idx_b)
        adjacency[idx_b].append(idx_a)
    
    # find root joint
    if hier_order:
        root_idx = pred_root_index
    else:
        centroid = np.mean(vertices, axis=0)
        distances = np.linalg.norm(pred_joints - centroid, axis=1)
        root_idx = np.argmin(distances)
    
    root_name = joint_names[root_idx]
    
    # build hierarchy
    parent_map = {}
    
    if hier_order:
        visited = set()
        
        for parent_idx, child_idx in pred_bones:
            if child_idx not in parent_map:
                parent_map[child_idx] = parent_idx
                visited.add(child_idx)
                visited.add(parent_idx)

        parent_map[root_idx] = None

    else:
        visited = set([root_idx])
        queue = deque([root_idx])
        parent_map[root_idx] = None
        
        while queue:
            current_idx = queue.popleft()
            for neighbor_idx in adjacency[current_idx]:
                if neighbor_idx not in visited:
                    parent_map[neighbor_idx] = current_idx
                    visited.add(neighbor_idx)
                    queue.append(neighbor_idx)
                
    if len(visited) != num_joints:
        print(f"bones are not fully connected, leaving {num_joints - len(visited)} joints unconnected.")
    
    # save joints
    joints_lines = []
    for idx, coord in enumerate(pred_joints):
        name = joint_names[idx]
        joints_line = f'joints {name} {coord[0]:.8f} {coord[1]:.8f} {coord[2]:.8f}'
        joints_lines.append(joints_line)
    
    # save root name
    root_line = f'root {root_name}'
    
    # save hierarchy
    hier_lines = []
    for child_idx, parent_idx in parent_map.items():
        if parent_idx is not None:
            parent_name = joint_names[parent_idx]
            child_name = joint_names[child_idx]
            hier_line = f'hier {parent_name} {child_name}'
            hier_lines.append(hier_line)
    
    with open(filename, 'w') as file:
        for line in joints_lines:
            file.write(line + '\n')

        file.write(root_line + '\n')

        for line in hier_lines:
            file.write(line + '\n')

def save_skeleton_obj(joints, bones, save_path, root_index=None, radius_sphere=0.01, 
                     radius_bone=0.005, segments=16, stacks=16, use_cone=False):
    """
    Save skeletons to obj file, each connection contains two red spheres (joint) and one blue cylinder (bone).
    if root index is known, set root sphere to green.
    """
    
    all_vertices = []
    all_colors = []
    all_faces = []
    vertex_offset = 0
    
    # create spheres for joints
    for i, joint in enumerate(joints):
        # define color
        if root_index is not None and i == root_index:
            color = (0, 1, 0)  # green for root joint
        else:
            color = (1, 0, 0)  # red for other joints
        
        # create joint sphere
        sphere_vertices, sphere_faces = create_sphere(joint, radius=radius_sphere, segments=segments, stacks=stacks)
        all_vertices.extend(sphere_vertices)
        all_colors.extend([color] * len(sphere_vertices))
        
        # adjust face index
        adjusted_sphere_faces = [(v1 + vertex_offset, v2 + vertex_offset, v3 + vertex_offset) for (v1, v2, v3) in sphere_faces]
        all_faces.extend(adjusted_sphere_faces)
        vertex_offset += len(sphere_vertices)
    
    # create bones
    for bone in bones:
        parent_idx, child_idx = bone
        parent = joints[parent_idx]
        child = joints[child_idx]
        
        try:
            bone_vertices, bone_faces = create_bone(parent, child, radius=radius_bone, segments=segments, use_cone=use_cone)
        except ValueError as e:
            print(f"Skipping connection {idx+1}, reason: {e}")
            continue
            
        all_vertices.extend(bone_vertices)
        all_colors.extend([(0, 0, 1)] * len(bone_vertices))  # blue
        
        # adjust face index
        adjusted_bone_faces = [(v1 + vertex_offset, v2 + vertex_offset, v3 + vertex_offset) for (v1, v2, v3) in bone_faces]
        all_faces.extend(adjusted_bone_faces)
        vertex_offset += len(bone_vertices)

    # save to obj
    obj_lines = []
    for v, c in zip(all_vertices, all_colors):
        obj_lines.append(f"v {v[0]} {v[1]} {v[2]} {c[0]} {c[1]} {c[2]}")
    obj_lines.append("") 

    for face in all_faces:
        obj_lines.append(f"f {face[0]} {face[1]} {face[2]}")
        
    with open(save_path, 'w') as obj_file:
        obj_file.write("\n".join(obj_lines))

def create_sphere(center, radius=0.01, segments=16, stacks=16):
    vertices = []
    faces = []
    for i in range(stacks + 1):
        lat = np.pi / 2 - i * np.pi / stacks
        xy = radius * np.cos(lat)
        z = radius * np.sin(lat)
        for j in range(segments):
            lon = j * 2 * np.pi / segments
            x = xy * np.cos(lon) + center[0]
            y = xy * np.sin(lon) + center[1]
            vertices.append((x, y, z + center[2]))
    for i in range(stacks):
        for j in range(segments):
            first = i * segments + j
            second = first + segments
            third = first + 1 if (j + 1) < segments else i * segments
            fourth = second + 1 if (j + 1) < segments else (i + 1) * segments
            faces.append((first + 1, second + 1, fourth + 1))
            faces.append((first + 1, fourth + 1, third + 1))
    return vertices, faces
    
def create_bone(start, end, radius=0.005, segments=16, use_cone=False):
    dir_vector = np.array(end) - np.array(start)
    height = np.linalg.norm(dir_vector)
    if height == 0:
        raise ValueError("Start and end points cannot be the same for a cone.")
    dir_vector = dir_vector / height

    z = np.array([0, 0, 1])
    if np.allclose(dir_vector, z):
        R = np.identity(3)
    elif np.allclose(dir_vector, -z):
        R = np.array([[-1,0,0],[0,-1,0],[0,0,1]])
    else:
        v = np.cross(z, dir_vector)
        s = np.linalg.norm(v)
        c = np.dot(z, dir_vector)
        kmat = np.array([[0, -v[2], v[1]],
                            [v[2], 0, -v[0]],
                            [-v[1], v[0], 0]])
        R = np.identity(3) + kmat + np.matmul(kmat, kmat) * ((1 - c) / (s**2))

    theta = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    base_circle = np.array([np.cos(theta), np.sin(theta), np.zeros(segments)]) * radius
    
    vertices = []
    for point in base_circle.T:
        rotated = np.dot(R, point) + np.array(start)
        vertices.append(tuple(rotated))
        

    faces = []
    
    if use_cone:
        vertices.append(tuple(end))

        apex_idx = segments + 1 
        for i in range(segments):
            next_i = (i + 1) % segments
            faces.append((i + 1, next_i + 1, apex_idx))
    else:
        top_circle = np.array([np.cos(theta), np.sin(theta), np.ones(segments)]) * radius
        for point in top_circle.T:
            point_scaled = np.array([point[0], point[1], height])
            rotated = np.dot(R, point_scaled) + np.array(start)
            vertices.append(tuple(rotated))
        for i in range(segments):
            next_i = (i + 1) % segments
            faces.append((i + 1, next_i + 1, next_i + segments + 1))
            faces.append((i + 1, next_i + segments + 1, i + segments + 1))
    
    return vertices, faces

def render_mesh_with_skeleton(joints, bones, vertices, faces, output_dir, filename, prefix='pred', root_idx=None):
    """
    Render the mesh with skeleton using PyRender.
    """
    loader = DataLoader()
    
    raw_size = (960, 960)
    renderer = PyRenderWrapper(raw_size)
    
    save_dir = os.path.join(output_dir, 'render_results')
    os.makedirs(save_dir, exist_ok=True)
    
    loader.joints = joints
    loader.bones = bones
    loader.root_idx = root_idx
    
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    mesh.visual.vertex_colors[:, 3] = 100  # set transparency
    loader.mesh = mesh
    v = mesh.vertices
    xmin, ymin, zmin = v.min(axis=0)
    xmax, ymax, zmax = v.max(axis=0)
    loader.bbox_center = np.array([(xmax + xmin)/2, (ymax + ymin)/2, (zmax + zmin)/2])
    loader.bbox_size = np.array([xmax - xmin, ymax - ymin, zmax - zmin])
    loader.bbox_scale = max(xmax - xmin, ymax - ymin, zmax - zmin)
    loader.normalize_coordinates()
    
    input_dict = loader.query_mesh_rig()
    
    angles = [0, np.pi/2, np.pi, 3*np.pi/2] 
    distance = np.max(loader.bbox_size) * 2
    
    subfolder_path = os.path.join(save_dir, filename + '_' + prefix)
    
    os.makedirs(subfolder_path, exist_ok=True)
    
    for i, angle in enumerate(angles):
        renderer.set_camera_view(angle, loader.bbox_center, distance)
        renderer.align_light_to_camera()

        color = renderer.render(input_dict)[0]
        
        output_filename = f"{filename}_{prefix}_view{i+1}.png"
        output_filepath = os.path.join(subfolder_path, output_filename)
        cv2.imwrite(output_filepath, color)
    

def save_args(args, output_dir, filename="config.json"):
    args_dict = vars(args)
    os.makedirs(output_dir, exist_ok=True)
    config_path = os.path.join(output_dir, filename)
    with open(config_path, 'w') as f:
        json.dump(args_dict, f, indent=4)