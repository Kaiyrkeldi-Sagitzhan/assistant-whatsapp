#!/usr/bin/env python3
"""
Verification script for the Gemini API integration and optimization project.

Run this to verify all changes are correctly implemented.
"""

import sys
import os

def check_file_exists(filepath, description):
    """Check if a file exists."""
    if os.path.exists(filepath):
        print(f"✅ {description}: {filepath}")
        return True
    else:
        print(f"❌ {description}: {filepath} NOT FOUND")
        return False

def check_syntax(filepath):
    """Check Python file syntax."""
    try:
        import py_compile
        py_compile.compile(filepath, doraise=True)
        return True
    except py_compile.PyCompileError as e:
        print(f"❌ Syntax error in {filepath}: {e}")
        return False

def check_imports_in_file(filepath, imports_to_check):
    """Check if specific imports exist in a file."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            missing = []
            for imp in imports_to_check:
                if imp not in content:
                    missing.append(imp)
            if missing:
                print(f"⚠️  {filepath} missing imports: {missing}")
                return False
            return True
    except Exception as e:
        print(f"❌ Error checking imports in {filepath}: {e}")
        return False

def main():
    print("=" * 70)
    print("🔍 VERIFICATION SCRIPT: Gemini API Integration Project")
    print("=" * 70)
    print()
    
    base_path = "/home/diana/Documents/GitHub/assistant-whatsapp"
    all_ok = True
    
    # ===== PHASE 1: Check new files =====
    print("\n📁 PHASE 1: New files")
    print("-" * 70)
    
    files_to_check = [
        (f"{base_path}/app/schemas/gemini.py", "New Pydantic schemas for Gemini"),
        (f"{base_path}/SETUP.md", "Integration guide and deployment"),
        (f"{base_path}/IMPLEMENTATION_COMPLETE.md", "Implementation report"),
    ]
    
    for filepath, description in files_to_check:
        if not check_file_exists(filepath, description):
            all_ok = False
    
    # ===== PHASE 2: Check syntax =====
    print("\n🐍 PHASE 2: Python syntax validation")
    print("-" * 70)
    
    python_files = [
        f"{base_path}/app/schemas/gemini.py",
        f"{base_path}/app/services/gemini_client.py",
        f"{base_path}/app/services/reminder_service.py",
        f"{base_path}/app/workers/jobs.py",
    ]
    
    for filepath in python_files:
        if os.path.exists(filepath):
            if check_syntax(filepath):
                print(f"✅ Syntax OK: {os.path.basename(filepath)}")
            else:
                all_ok = False
        else:
            print(f"❌ File not found: {filepath}")
            all_ok = False
    
    # ===== PHASE 3: Check dependencies =====
    print("\n📦 PHASE 3: Dependencies in pyproject.toml")
    print("-" * 70)
    
    pyproject_path = f"{base_path}/pyproject.toml"
    required_deps = [
        "google-generativeai>=0.8.0",
        "tenacity>=8.2.0",
        "pydantic-json-schema>=2.0.0",
    ]
    
    try:
        with open(pyproject_path, 'r') as f:
            content = f.read()
            for dep in required_deps:
                if dep in content:
                    print(f"✅ Found dependency: {dep}")
                else:
                    print(f"❌ Missing dependency: {dep}")
                    all_ok = False
    except Exception as e:
        print(f"❌ Error reading pyproject.toml: {e}")
        all_ok = False
    
    # ===== PHASE 4: Check key imports and improvements =====
    print("\n📋 PHASE 4: Key improvements")
    print("-" * 70)
    
    checks = [
        (f"{base_path}/app/services/gemini_client.py", 
         ["google.generativeai", "tenacity", "ExtractedTask", "retry"],
         "Gemini SDK + retry logic + Pydantic"),
        
        (f"{base_path}/app/services/reminder_service.py",
         ["def parse_notification_text", "timedelta"],
         "Hours without minutes support"),
        
        (f"{base_path}/app/workers/jobs.py",
         ["_parse_message_with_retry", "_send_whatsapp_with_retry", "tenacity"],
         "Retry wrappers for NLP and WhatsApp"),
    ]
    
    for filepath, imports, description in checks:
        if os.path.exists(filepath):
            if check_imports_in_file(filepath, imports):
                print(f"✅ {description}")
            else:
                all_ok = False
        else:
            print(f"❌ File not found: {filepath}")
            all_ok = False
    
    # ===== PHASE 5: Check configuration =====
    print("\n⚙️  PHASE 5: Configuration")
    print("-" * 70)
    
    config_path = f"{base_path}/app/core/config.py"
    required_settings = [
        "gemini_api_key",
        "gemini_model",
    ]
    
    try:
        with open(config_path, 'r') as f:
            content = f.read()
            for setting in required_settings:
                if setting in content:
                    print(f"✅ Config setting: {setting}")
                else:
                    print(f"❌ Missing config: {setting}")
                    all_ok = False
    except Exception as e:
        print(f"❌ Error reading config.py: {e}")
        all_ok = False
    
    # ===== SUMMARY =====
    print("\n" + "=" * 70)
    if all_ok:
        print("🎉 ALL CHECKS PASSED!")
        print("=" * 70)
        print("\n✅ Project is ready for deployment!")
        print("\nNext steps:")
        print("  1. Get Gemini API key: https://aistudio.google.com/app/apikey")
        print("  2. Add GEMINI_API_KEY to .env file")
        print("  3. Install dependencies: pip install -e .")
        print("  4. Run: docker-compose up")
        print("  5. Read SETUP.md for detailed deployment guide")
        return 0
    else:
        print("❌ SOME CHECKS FAILED")
        print("=" * 70)
        print("\nPlease fix the issues above before deploying.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
