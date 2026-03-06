#!/usr/bin/env python3
"""Test script to validate all environment variables and settings."""

from pathlib import Path
from src.config.settings import get_settings


def parse_env_file(filepath):
    """Parse .env.example file to extract variable names and descriptions."""
    variables = {}
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key = line.split("=")[0].strip()
                variables[key] = line
    return variables


def get_settings_attributes():
    """Get all settings attributes and their values."""
    settings = get_settings()
    attrs = {}
    for attr in dir(settings):
        if not attr.startswith("_") and attr.upper() == attr:
            try:
                value = getattr(settings, attr)
                attrs[attr] = value
            except Exception as e:
                attrs[attr] = f"ERROR: {e}"
    return attrs


def compare_env_and_settings():
    """Compare .env.example variables with loaded settings."""
    env_file = Path(__file__).parent / ".env.example"

    print("=" * 80)
    print("ENVIRONMENT VARIABLES AND SETTINGS VALIDATION")
    print("=" * 80)

    # Parse .env.example
    env_vars = parse_env_file(env_file)
    print(f"\n✓ Found {len(env_vars)} variables in .env.example")

    # Get loaded settings
    settings = get_settings()

    # Check each setting
    print("\n" + "=" * 80)
    print("CHECKING SETTINGS")
    print("=" * 80)

    # Get field info from settings
    settings_dict = settings.model_dump()
    print(f"\n✓ Loaded {len(settings_dict)} settings from Settings class")

    # Map env vars to settings (convert to lowercase)
    env_to_settings = {}
    for env_key in env_vars.keys():
        settings_key = env_key.lower()
        env_to_settings[env_key] = settings_key

    # Check each setting
    missing_in_settings = []
    present_in_settings = []

    for env_key, settings_key in env_to_settings.items():
        if settings_key in settings_dict:
            value = settings_dict[settings_key]
            present_in_settings.append(
                {
                    "env_key": env_key,
                    "settings_key": settings_key,
                    "value": value,
                    "type": type(value).__name__,
                }
            )
        else:
            missing_in_settings.append(env_key)

    # Display results
    print("\n" + "-" * 80)
    print("VARIABLES LOADED INTO SETTINGS")
    print("-" * 80)
    for item in sorted(present_in_settings, key=lambda x: x["env_key"]):
        print(f"✓ {item['env_key']:40} = {str(item['value'])[:40]:40} ({item['type']})")

    if missing_in_settings:
        print("\n" + "-" * 80)
        print("⚠️  VARIABLES NOT FOUND IN SETTINGS")
        print("-" * 80)
        for var in sorted(missing_in_settings):
            print(f"✗ {var}")

    # Check for settings not in .env.example
    settings_not_in_env = []
    for settings_key in settings_dict.keys():
        env_key = settings_key.upper()
        if env_key not in env_vars:
            settings_not_in_env.append(
                {
                    "settings_key": settings_key,
                    "env_key": env_key,
                    "value": settings_dict[settings_key],
                    "type": type(settings_dict[settings_key]).__name__,
                }
            )

    if settings_not_in_env:
        print("\n" + "-" * 80)
        print("⚠️  SETTINGS NOT DOCUMENTED IN .env.example")
        print("-" * 80)
        for item in sorted(settings_not_in_env, key=lambda x: x["settings_key"]):
            print(f"✗ {item['env_key']:40} ({item['settings_key']:40}) = {str(item['value'])[:40]}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total .env.example variables: {len(env_vars)}")
    print(f"Settings loaded:              {len(present_in_settings)}")
    print(f"Missing from settings:        {len(missing_in_settings)}")
    print(f"Not in .env.example:          {len(settings_not_in_env)}")
    print(
        f"Match status:                 {'✓ PASS' if not missing_in_settings and not settings_not_in_env else '⚠️  NEEDS REVIEW'}"
    )
    print("=" * 80)


if __name__ == "__main__":
    compare_env_and_settings()
