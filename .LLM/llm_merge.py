import os
import sys
from datetime import datetime
from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern

# Header template
header = f"""This file is a merged representation of the entire codebase, combining all repository files into a single document.
Generated on: {datetime.utcnow().isoformat()}

================================================================
Purpose:
--------
This file is designed for efficient processing by LLMs, providing a packed 
representation of all code files in the repository.

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

def load_gitignore(directory):
    """
    Load .gitignore from the specified directory, if it exists,
    and return a PathSpec. Otherwise return None.
    """
    gitignore_path = os.path.join(directory, '.gitignore')
    if os.path.exists(gitignore_path):
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            return PathSpec.from_lines(GitWildMatchPattern, f.readlines())
    return None

def load_exclude_patterns(directory):
    """
    Load exclude.yml from the specified directory, if it exists,
    and return a PathSpec. Otherwise return None.
    """
    exclude_path = os.path.join(directory, 'exclude.yml')
    if os.path.exists(exclude_path):
        with open(exclude_path, 'r', encoding='utf-8') as f:
            # Filter out comments and empty lines
            patterns = [
                line.strip()
                for line in f.readlines()
                if line.strip() and not line.strip().startswith('#')
            ]
            return PathSpec.from_lines(GitWildMatchPattern, patterns)
    return None

def should_exclude(path, base_dir, exclude_spec, gitignore_spec):
    """
    Check if a path should be excluded either by exclude.yml patterns or .gitignore patterns.
    """
    rel_path = os.path.relpath(path, base_dir)

    # Check exclude.yml patterns first
    if exclude_spec and exclude_spec.match_file(rel_path):
        return True

    # Then check .gitignore patterns if available
    if gitignore_spec and gitignore_spec.match_file(rel_path):
        return True

    return False

def generate_repository_structure(directory, gitignore_spec, exclude_spec):
    """
    Generate a textual "tree" of the repository structure, respecting exclude rules.
    """
    structure_lines = []
    for root, dirs, files in os.walk(directory):
        # Filter out excluded directories
        dirs[:] = [
            d for d in dirs
            if not should_exclude(os.path.join(root, d), directory, exclude_spec, gitignore_spec)
        ]

        indent_level = os.path.relpath(root, directory).count(os.sep)
        # If we're at the top-level, relpath might be '.', so handle that cleanly
        dirname = '.' if root == directory else os.path.basename(root)
        structure_lines.append("    " * indent_level + dirname + "/")

        for file in files:
            file_path = os.path.join(root, file)
            if not should_exclude(file_path, directory, exclude_spec, gitignore_spec):
                structure_lines.append("    " * (indent_level + 1) + file)

    return "\n".join(structure_lines)

def merge_files(src_directory, output_directory, output_prefix):
    """
    Merges all non-excluded files into a single text file. Respects exclude patterns.
    Writes the output to `output_directory`, ensuring we don't re-include that output.
    """
    gitignore_spec = load_gitignore(src_directory)
    exclude_spec = load_exclude_patterns(os.path.join(src_directory, '.LLM'))

    # Build the final set of patterns in memory so the new output file doesn't get re-included
    additional_excludes = []
    # We'll exclude the final output file name explicitly, just in case:
    merged_name = f"{output_prefix}.txt"
    additional_excludes.append(merged_name)
    # Convert them into PathSpec lines and combine with existing exclude patterns:
    # (We only do this if exclude_spec isn't None; otherwise we create a new one.)
    extra_spec = PathSpec.from_lines(GitWildMatchPattern, additional_excludes)

    # Combine patterns if we already had some
    if exclude_spec:
        patterns_combined = exclude_spec.patterns + extra_spec.patterns
        exclude_spec = PathSpec(patterns=patterns_combined)
    else:
        exclude_spec = extra_spec

    # Generate a repository structure overview
    repository_structure = generate_repository_structure(src_directory, gitignore_spec, exclude_spec)

    # Prepare the full output text in memory
    output_lines = [
        header,
        repository_structure,
        ""
    ]

    valid_files = []
    for root, dirs, files in os.walk(src_directory):
        # Exclude directories inline
        dirs[:] = [
            d for d in dirs
            if not should_exclude(os.path.join(root, d), src_directory, exclude_spec, gitignore_spec)
        ]

        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, src_directory)
            # Skip excluded files or files in excluded dirs
            if should_exclude(file_path, src_directory, exclude_spec, gitignore_spec):
                continue

            # Also skip if any of this file's parent directories are excluded
            parents = rel_path.split(os.sep)[:-1]
            if any(
                should_exclude(os.path.join(src_directory, p), src_directory, exclude_spec, gitignore_spec)
                for p in parents
            ):
                continue

            valid_files.append(file_path)

    for file_path in valid_files:
        relative_path = os.path.relpath(file_path, src_directory)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            output_lines.append("================================================================")
            output_lines.append(f"###START_FILE_PATH: {relative_path}###")
            output_lines.append(content)
            output_lines.append("###END_FILE###\n")
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

    # Finally write out the merged file
    final_output_path = os.path.join(output_directory, merged_name)
    with open(final_output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))

    print(f"Created {final_output_path}")

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)

    # Default output prefix
    output_prefix = "merged_output"
    if len(sys.argv) > 1:
        output_prefix = sys.argv[1]

    print(f"Scanning directory: {parent_dir}")
    print(f"Output will be saved in: {script_dir}")
    print(f"Output prefix: {output_prefix}")
    print(f"Using exclude patterns from: {os.path.join(parent_dir, '.LLM', 'exclude.yml')}")

    merge_files(parent_dir, script_dir, output_prefix)