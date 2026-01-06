import os
from pathlib import Path

def create_structure():
    """
    Creates the folder structure for the refactored project.
    """
    root = Path.cwd()
    print(f"Scaffolding structure in: {root}")

    # Define the directory tree
    directories = [
        "dedupe/core",
        "dedupe/storage",
        "dedupe/utils",
        "dedupe/external",
        "tools/integrity",
        "tools/decide",
        "tools/review",
        "tools/ingest",  # Renamed from 'import' to avoid keyword conflict, or matching existing structure
        "tests/core",
        "tests/storage",
        "tests/utils",
        "tests/tools",
        "docs/plans",
        "docs/status",
        "scripts",
    ]

    # Define files to touch (create empty if not exist)
    files = [
        # Core Packages
        "dedupe/__init__.py",
        "dedupe/core/__init__.py",
        "dedupe/storage/__init__.py",
        "dedupe/utils/__init__.py",
        "dedupe/external/__init__.py",
        
        # Tool Packages (Optional, but good for testing)
        "tools/__init__.py",
        "tools/integrity/__init__.py",
        "tools/decide/__init__.py",
        "tools/review/__init__.py",
        "tools/ingest/__init__.py",

        # Test Packages
        "tests/__init__.py",
        "tests/core/__init__.py",
        "tests/storage/__init__.py",
        "tests/utils/__init__.py",
        "tests/tools/__init__.py",
        
        # Config
        "config.toml",
    ]

    # 1. Create Directories
    for d in directories:
        path = root / d
        try:
            path.mkdir(parents=True, exist_ok=True)
            print(f"✔  Created dir: {d}")
        except Exception as e:
            print(f"✘  Error creating {d}: {e}")

    # 2. Create Files
    for f in files:
        path = root / f
        if not path.exists():
            try:
                path.touch()
                print(f"✔  Created file: {f}")
            except Exception as e:
                print(f"✘  Error creating {f}: {e}")
        else:
            print(f"•  Exists: {f}")

    print("\nStructure setup complete.")
    print("Next: Move your refactored code into the corresponding files.")

if __name__ == "__main__":
    create_structure()
