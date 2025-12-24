Please execute the 'Update Brewfile' workflow:

1. Run `./dotfiles/scripts/brew/brew-manager.sh capture` to update the Brewfile.
2. Check for changes in `dotfiles/scripts/brew/Brewfile`.
3. If changed:
   a. Commit the change in the `dotfiles` submodule with message: "chore(brew): update Brewfile with current system state"
   b. Update the submodule reference in the main repo with message: "chore: update dotfiles submodule (Brewfile sync)"
4. If no changes, let the user know.
