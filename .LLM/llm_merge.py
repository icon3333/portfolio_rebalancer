import os
import sys
import re
from datetime import datetime

# Header template for the merged output file
header = f"""This file is a merged representation of selected files from the codebase.
Generated on: {datetime.utcnow().isoformat()}

================================================================
Purpose:
--------
This file is designed for efficient processing by LLMs, providing a packed 
representation of selected code files in the repository.

Format:
-------
- This summary section
- Repository structure
- File sections, each consisting of:
  - A separator line (================)
  - The file path (###START_FILE_PATH: path/to/file###)
  - File contents
  - ###END_FILE###

================================================================
Repository Structure
================================================================
"""

def is_binary_file(file_path):
    """
    Check if a file is binary by reading its first few bytes.
    """
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
            return b'\0' in chunk  # Simple check for null bytes
    except Exception as e:
        print(f"ERROR checking if file is binary: {file_path} - {str(e)}")
        return True  # Assume binary on error

def should_exclude_path(path, base_dir, exclude_patterns):
    """
    Determine if a path should be excluded based on the exclude patterns.
    """
    # Normalize path for consistent matching (convert backslashes to forward slashes)
    rel_path = os.path.relpath(path, base_dir).replace('\\', '/')
    
    # Check each exclude pattern
    for pattern in exclude_patterns:
        # Special handling for _*/ pattern
        if pattern == '_*/':
            path_parts = rel_path.split('/')
            if any(part.startswith('_') for part in path_parts):
                return True
        
        # If pattern ends with /, it's a directory pattern - exclude anything inside it
        if pattern.endswith('/') and rel_path.startswith(pattern):
            return True
            
        # Handle wildcard patterns with regex
        if '*' in pattern:
            # Convert glob pattern to regex pattern
            regex_pattern = pattern.replace('.', '\\.').replace('*', '.*')
            if re.match(f"^{regex_pattern}$", rel_path):
                return True
    
    return False

def find_files_with_wildcard(base_dir, pattern):
    """
    Find all files that match a pattern with wildcard.
    Returns a list of relative paths for matching files.
    """
    matching_files = []
    
    # If no wildcard, just return the pattern itself if it exists
    if '*' not in pattern:
        full_path = os.path.join(base_dir, pattern)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            return [pattern]
        return []
    
    # Convert glob pattern to regex
    pattern_parts = pattern.split('/')
    dir_parts = pattern_parts[:-1]
    file_pattern = pattern_parts[-1]
    
    # Build the base directory path for searching
    search_dir = base_dir
    if dir_parts:
        if '*' in '/'.join(dir_parts):
            # Complex case: directory part contains wildcards
            print(f"WARNING: Directory wildcards are complex, doing basic matching for: {pattern}")
            # Use simplified glob-like matching for these cases
            for root, _, files in os.walk(base_dir):
                rel_root = os.path.relpath(root, base_dir).replace('\\', '/')
                for file in files:
                    rel_path = os.path.join(rel_root, file).replace('\\', '/')
                    # Convert glob pattern to regex for matching
                    regex_pattern = pattern.replace('.', '\\.').replace('*', '.*')
                    if re.match(f"^{regex_pattern}$", rel_path):
                        matching_files.append(rel_path)
            return matching_files
        else:
            # Simple case: only filename has wildcard
            search_dir = os.path.join(base_dir, '/'.join(dir_parts))
    
    # If search directory doesn't exist, return empty list
    if not os.path.exists(search_dir):
        print(f"WARNING: Search directory not found: {search_dir}")
        return []
    
    # Create regex pattern for filename matching
    file_regex = '^' + file_pattern.replace('.', '\\.').replace('*', '.*') + '$'
    
    # Find all files in the directory that match the pattern
    for file in os.listdir(search_dir):
        file_path = os.path.join(search_dir, file)
        if os.path.isfile(file_path) and re.match(file_regex, file):
            # Calculate relative path
            if dir_parts:
                rel_path = '/'.join(dir_parts) + '/' + file
            else:
                rel_path = file
            matching_files.append(rel_path)
    
    return matching_files

def parse_config_file(config_path):
    """
    Parse the config.yml file to extract focus files and exclude patterns.
    Returns a tuple of (focus_files, exclude_patterns).
    """
    focus_files = []
    exclude_patterns = []
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        mode = None
        for line in lines:
            # Strip whitespace
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Check for section markers
            if line == "# Focus":
                mode = "focus"
                continue
            elif line == "# Exclude":
                mode = "exclude"
                continue
            
            # Skip comments
            if line.startswith('#'):
                continue
            
            # Add to appropriate list based on current mode
            if mode == "focus":
                focus_files.append(line)
            elif mode == "exclude":
                exclude_patterns.append(line)
    
    except Exception as e:
        print(f"ERROR reading config file: {str(e)}")
    
    return focus_files, exclude_patterns

def find_focus_files(base_dir, focus_paths, exclude_patterns):
    """
    Find and validate the specified focus files, including wildcard expansion.
    Returns a list of (full_path, relative_path) tuples for valid focus files.
    """
    valid_files = []
    
    # Process each focus path, expanding wildcards
    for focus_path in focus_paths:
        # Check if path contains wildcards
        if '*' in focus_path:
            # Expand wildcard to find matching files
            matching_paths = find_files_with_wildcard(base_dir, focus_path)
            print(f"Wildcard pattern '{focus_path}' matched {len(matching_paths)} files")
            
            # Process each matching file
            for match_path in matching_paths:
                # Get full path
                full_path = os.path.join(base_dir, match_path)
                rel_path = match_path.replace('\\', '/')
                
                # Validate the file
                if process_single_file(full_path, rel_path, base_dir, exclude_patterns):
                    valid_files.append((full_path, rel_path))
                    print(f"Including expanded focus file: {rel_path}")
        else:
            # Regular file path without wildcards
            full_path = os.path.join(base_dir, focus_path)
            rel_path = focus_path.replace('\\', '/')
            
            # Validate the file
            if process_single_file(full_path, rel_path, base_dir, exclude_patterns):
                valid_files.append((full_path, rel_path))
                print(f"Including focus file: {rel_path}")
    
    return valid_files

def process_single_file(full_path, rel_path, base_dir, exclude_patterns):
    """
    Process and validate a single file.
    Returns True if the file is valid and should be included.
    """
    # Check if file exists
    if not os.path.exists(full_path):
        print(f"WARNING: Focus file not found: {rel_path}")
        print(f"  Full path tried: {full_path}")
        return False
    
    # Check if file should be excluded
    if should_exclude_path(full_path, base_dir, exclude_patterns):
        print(f"WARNING: Focus file matches exclude pattern: {rel_path}")
        return False
    
    # Check if file is a directory
    if os.path.isdir(full_path):
        print(f"WARNING: Focus path is a directory, not a file: {rel_path}")
        return False
    
    # Check if file is binary
    if is_binary_file(full_path):
        print(f"WARNING: Focus file appears to be binary: {rel_path}")
        return False
    
    # All checks passed
    return True

def collect_directory_structure(files):
    """
    Generate a directory structure based on the included files.
    """
    # Build a tree representation
    tree = {}
    for _, rel_path in files:
        parts = rel_path.split('/')
        current = tree
        # Build directory structure
        for i, part in enumerate(parts):
            if i == len(parts) - 1:  # Last part is file
                if '__files__' not in current:
                    current['__files__'] = []
                current['__files__'].append(part)
            else:  # Directories
                if part not in current:
                    current[part] = {}
                current = current[part]
    
    # Create lines for output
    structure_lines = ["./"]
    
    # Recursive function to build structure lines
    def build_structure(node, prefix, depth):
        lines = []
        
        # Add directories first (sorted)
        for name in sorted([k for k in node.keys() if k != '__files__']):
            lines.append(prefix + name + "/")
            sub_lines = build_structure(node[name], prefix + "    ", depth + 1)
            lines.extend(sub_lines)
        
        # Add files (sorted)
        if '__files__' in node:
            for file in sorted(node['__files__']):
                lines.append(prefix + file)
        
        return lines
    
    # Build the structure lines
    structure_lines.extend(build_structure(tree, "    ", 1))
    
    return "\n".join(structure_lines)

def merge_files(base_dir, output_dir, output_prefix, config_path):
    """
    Main function to merge files using the config file
    """
    # Parse config file to get focus paths and exclude patterns
    focus_paths, exclude_patterns = parse_config_file(config_path)
    
    print("Configuration from file:")
    print(f"Focus paths: {focus_paths}")
    print(f"Exclude patterns: {exclude_patterns}")
    
    # Process focus files, expanding wildcards
    print(f"\nFOCUS MODE: Will include files matching {len(focus_paths)} specified patterns")
    files_to_include = find_focus_files(base_dir, focus_paths, exclude_patterns)
    
    # If no files to include, exit
    if not files_to_include:
        print("ERROR: No valid files to include. Check focus files and exclude patterns.")
        return
    
    # Generate repository structure
    print(f"\nGenerating repository structure for {len(files_to_include)} files")
    repo_structure = collect_directory_structure(files_to_include)
    
    # Prepare output content
    output_lines = [
        header,
        repo_structure,
        ""
    ]
    
    # Process files
    print("\nProcessing files:")
    for full_path, rel_path in files_to_include:
        try:
            # Read and add file content
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            output_lines.append("================================================================")
            output_lines.append(f"###START_FILE_PATH: {rel_path}###")
            output_lines.append(content)
            output_lines.append("###END_FILE###\n")
            print(f"  Added: {rel_path}")
        
        except Exception as e:
            print(f"  ERROR reading {rel_path}: {str(e)}")
    
    # Write output file
    output_file = f"{output_prefix}.txt"
    output_path = os.path.join(output_dir, output_file)
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output_lines))
        print(f"\nCreated {output_path} with {len(files_to_include)} files")
    except Exception as e:
        print(f"ERROR creating output file {output_path}: {str(e)}")
        # Try with a different approach
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                for line in output_lines:
                    f.write(line + '\n')
            print(f"\nCreated {output_path} (alternative method) with {len(files_to_include)} files")
        except Exception as e2:
            print(f"ERROR on second attempt: {str(e2)}")

if __name__ == "__main__":
    # Get script directory and parent directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    
    # Print current working directory
    print(f"Current working directory: {os.getcwd()}")
    print(f"Script directory: {script_dir}")
    print(f"Parent directory: {parent_dir}")
    
    # Get output prefix from command line args
    output_prefix = "merged_output"
    if len(sys.argv) > 1 and not sys.argv[1].startswith('--'):
        output_prefix = sys.argv[1]
    
    print(f"Repository merger script starting:")
    print(f"  Base directory: {parent_dir}")
    print(f"  Output directory: {script_dir}")
    print(f"  Output file: {output_prefix}.txt\n")
    
    # Check existing config.yml
    config_path = os.path.join(script_dir, 'config.yml')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Existing config.yml contains {len(content)} bytes:")
            print("-" * 40)
            print(content)
            print("-" * 40)
            
            # Merge files using config file
            merge_files(parent_dir, script_dir, output_prefix, config_path)
        except Exception as e:
            print(f"Error reading config.yml: {str(e)}")
            sys.exit(1)
    else:
        print(f"ERROR: Config file not found: {config_path}")