# auto_env.py
"""
Automatic .env.example generator
Creates .env.example file from .env without real API keys
"""

from pathlib import Path

def create_env_example():
    """Create .env.example file from .env"""
    
    env_path = Path(__file__).resolve().parent / ".env"
    example_path = Path(__file__).resolve().parent / ".env.example"
    
    # Check if .env exists
    if not env_path.exists():
        print("❌ .env file not found!")
        print("   Please create .env file with your API keys first")
        return False
    
    # Read .env file
    with open(env_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace API keys with placeholder texts
    lines = content.splitlines()
    new_lines = []
    
    for line in lines:
        if not line.strip() or line.startswith('#'):
            # Keep comments and empty lines
            new_lines.append(line)
        elif '=' in line:
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            
            # Check if it's an API key
            if 'API_KEY' in key or 'KEY' in key:
                # Replace with placeholder
                if 'OPENSUBTITLES' in key:
                    new_lines.append(f"{key}=your_opensubtitles_api_key_here")
                elif 'TMDB' in key:
                    new_lines.append(f"{key}=your_tmdb_api_key_here")
                else:
                    new_lines.append(f"{key}=your_api_key_here")
            elif 'USERNAME' in key:
                new_lines.append(f"{key}=your_username_here")
            elif 'PASSWORD' in key:
                new_lines.append(f"{key}=your_password_here")
            else:
                # Keep other lines
                new_lines.append(line)
    
    # Write .env.example
    with open(example_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))
    
    print("✅ .env.example created successfully!")
    print(f"   File: {example_path}")
    print("   Remember to add it to version control (git add .env.example)")
    return True

def show_example_content():
    """Show .env.example content"""
    example_path = Path(__file__).resolve().parent / ".env.example"
    
    if example_path.exists():
        print("\n📄 .env.example content:")
        print("-" * 50)
        with open(example_path, 'r', encoding='utf-8') as f:
            print(f.read())
        print("-" * 50)
    else:
        print("❌ .env.example not found")

def main():
    """Main function"""
    print("🔄 Generating .env.example...")
    print("")
    
    if create_env_example():
        print("")
        show_example_content()
        print("")
        print("💡 Tip: Add .env.example to version control:")
        print("   git add .env.example")
        print("   git commit -m 'Add .env.example template'")
    else:
        print("")
        print("⚠️  .env.example creation failed!")

if __name__ == "__main__":
    main()