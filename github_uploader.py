import subprocess
import os

def upload_image_to_github(filepath):
    try:
        if not os.path.exists(filepath):
            print(f"[github_uploader] File not found: {filepath}")
            return None
            
        # Run git commands to stage, commit, and push the file
        subprocess.run(["git", "add", filepath], check=True, stdout=subprocess.DEVNULL)
        
        # Check if there are changes to commit
        status = subprocess.run(["git", "status", "--porcelain", filepath], capture_output=True, text=True, check=True)
        if not status.stdout.strip():
            # No changes, but we still return the raw github URL
            pass
        else:
            filename = os.path.basename(filepath)
            subprocess.run(["git", "commit", "-m", f"Update chart {filename}"], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "push"], check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        # Construct the raw github url
        remote_url = subprocess.run(["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True, check=True).stdout.strip()
        
        if "github.com" in remote_url:
            parts = remote_url.split("github.com")[-1].strip(":/").replace(".git", "").split("/")
            if len(parts) >= 2:
                owner, repo = parts[0], parts[1]
                branch = "main"
                try:
                    branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True).stdout.strip() or "main"
                except:
                    pass
                return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filepath.replace(os.sep, '/')}"
        return None
    except subprocess.TimeoutExpired:
        print("[FAIL] Git Push Timed Out (Auth required?)")
        return None
    except Exception as e:
        print(f"[FAIL] Custom Upload Error: {e}")
        return None

if __name__ == "__main__":
    # Test (Dry run concept, real run requires file)
    pass
