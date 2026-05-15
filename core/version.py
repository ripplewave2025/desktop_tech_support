"""
Single source of truth for the Zora version string.

Anyone who needs the version (launcher banner, crash reports, /api/update,
the GitHub release tag matcher) should import from here. That way bumping
the version is a one-line change.

The version follows ``MAJOR.MINOR.PATCH`` semver. Releases are tagged in
GitHub as ``v{ZORA_VERSION}`` so the auto-updater's tag parsing matches.
"""

ZORA_VERSION = "2.3.1"
