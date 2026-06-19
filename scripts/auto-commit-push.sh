#!/bin/bash

# Script for automatically committing and pushing changes
# Then running the release automation

set -e  # Exit on any error

echo "🔄 Auto commit and push script"

# Check if there are any changes
if [[ -z $(git status -s) ]]; then
    echo "✅ No changes to commit"
    exit 0
fi

# Get commit message from argument or use default
COMMIT_MESSAGE="${1:-Auto commit changes}"

echo "📝 Committing changes: $COMMIT_MESSAGE"

# Add all changes
git add .

# Commit changes
git commit -m "$COMMIT_MESSAGE"

# Push changes
echo "📤 Pushing changes..."
git push origin HEAD

echo "✅ Changes committed and pushed successfully!"

# Run release automation if requested
if [[ "$2" == "--release" ]]; then
    echo "🚀 Running release automation..."
    ./scripts/release.sh
fi

exit 0