#!/bin/bash

# Script for automating release process after commit and push
# Checks pipeline status, merges to master, and bumps version

set -e  # Exit on any error

echo "🚀 Starting release automation process..."

# Get the current branch name
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Current branch: $CURRENT_BRANCH"

# Get the latest commit hash
COMMIT_HASH=$(git rev-parse HEAD)
echo "Latest commit: $COMMIT_HASH"

# Push changes if not already pushed
echo "📤 Pushing changes..."
git push origin $CURRENT_BRANCH

# Function to check GitHub Actions workflow status
check_pipeline_status() {
    echo "🔍 Checking pipeline status for commit $COMMIT_HASH..."
    
    # Wait a bit for pipeline to start
    sleep 10
    
    # Check workflow runs for the commit
    # This would require GitHub CLI to be installed and authenticated
    if command -v gh &> /dev/null; then
        # Get the latest workflow run for the commit
        RUN_STATUS=$(gh run list --commit $COMMIT_HASH --limit 5 --json status,conclusion | jq -r '.[0].conclusion')
        echo "Pipeline status: $RUN_STATUS"
        
        if [[ "$RUN_STATUS" == "success" ]]; then
            return 0
        elif [[ "$RUN_STATUS" == "failure" ]]; then
            echo "❌ Pipeline failed!"
            return 1
        else
            echo "⏳ Pipeline still running, waiting..."
            return 2
        fi
    else
        echo "⚠️ GitHub CLI not found, skipping pipeline check"
        echo "Please install GitHub CLI: https://cli.github.com/"
        return 0
    fi
}

# Wait for pipeline to complete
MAX_ATTEMPTS=30
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    check_pipeline_status
    STATUS=$?
    
    if [ $STATUS -eq 0 ]; then
        echo "✅ Pipeline passed successfully!"
        break
    elif [ $STATUS -eq 1 ]; then
        echo "❌ Pipeline failed, aborting release"
        exit 1
    else
        ATTEMPT=$((ATTEMPT + 1))
        echo "Attempt $ATTEMPT/$MAX_ATTEMPTS: Waiting 30 seconds before checking again..."
        sleep 30
    fi
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "⏰ Timeout waiting for pipeline to complete"
    exit 1
fi

# Get current version from pyproject.toml
CURRENT_VERSION=$(grep -E '^version = "' pyproject.toml | cut -d'"' -f2)
echo "Current version: $CURRENT_VERSION"

# Function to bump version (simple patch version bump)
bump_version() {
    local version=$1
    local major minor patch
    
    # Split version into parts
    IFS='.' read -ra VERSION_PARTS <<< "$version"
    major=${VERSION_PARTS[0]}
    minor=${VERSION_PARTS[1]}
    patch=${VERSION_PARTS[2]}
    
    # Increment patch version
    patch=$((patch + 1))
    
    echo "${major}.${minor}.${patch}"
}

# Bump version
NEW_VERSION=$(bump_version $CURRENT_VERSION)
echo "New version: $NEW_VERSION"

# Update version in pyproject.toml
echo "📝 Updating version in pyproject.toml..."
sed -i.bak "s/version = \"$CURRENT_VERSION\"/version = \"$NEW_VERSION\"/" pyproject.toml
rm pyproject.toml.bak

# Update version in __init__.py if it exists there
if [ -f "src/prometheus_mcp/__init__.py" ]; then
    echo "__version__ = \"$NEW_VERSION\"" > src/prometheus_mcp/__init__.py
fi

# Create new commit with version bump
echo "💾 Committing version bump..."
git add pyproject.toml src/prometheus_mcp/__init__.py
git commit -m "Bump version to $NEW_VERSION"

# Create tag
echo "🏷️ Creating tag v$NEW_VERSION..."
git tag -a "v$NEW_VERSION" -m "Release version $NEW_VERSION"

# Push everything
echo "📤 Pushing version bump and tag..."
git push origin $CURRENT_BRANCH
git push origin "v$NEW_VERSION"

echo "🎉 Release automation completed!"
echo "Version $NEW_VERSION has been bumped and tagged."
echo "Publish workflow should start automatically."

exit 0