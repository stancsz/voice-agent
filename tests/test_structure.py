import os
import sys

def test_files_exist():
    expected_files = [
        "requirements.txt",
        "Dockerfile",
        "docker-compose.yml",
        "bot.py",
        "entrypoint.sh"
    ]
    missing = []
    for f in expected_files:
        if not os.path.exists(f):
            missing.append(f)

    if missing:
        print(f"FAILED: Missing files: {missing}")
        sys.exit(1)
    else:
        print("PASSED: All expected files exist.")

def test_bot_syntax():
    try:
        with open("bot.py", "r") as f:
            content = f.read()
        compile(content, "bot.py", "exec")
        print("PASSED: bot.py syntax is correct.")
    except Exception as e:
        print(f"FAILED: bot.py syntax error: {e}")
        sys.exit(1)

def test_dockerfile_content():
    required_keywords = ["FROM python:", "apt-get", "pip install", "ENTRYPOINT"]
    with open("Dockerfile", "r") as f:
        content = f.read()

    missing = [kw for kw in required_keywords if kw not in content]
    if missing:
        print(f"FAILED: Dockerfile missing keywords: {missing}")
        sys.exit(1)
    else:
        print("PASSED: Dockerfile contains required keywords.")

if __name__ == "__main__":
    test_files_exist()
    test_bot_syntax()
    test_dockerfile_content()
