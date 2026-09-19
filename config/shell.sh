# work-ledger shell helpers. Source from ~/.bashrc or ~/.zshrc:
#   source ~/.work-ledger/config/shell.sh

# Which ssh aliases to also read sessions from (set on the laptop, leave empty on the VM).
# export WORK_LEDGER_REMOTES="vm"

# Optional: log each finished session to today's Obsidian daily note.
# export WORK_LEDGER_OBSIDIAN_DAILY_DIR="$HOME/path/to/vault"

# cd into a past session's folder without starting Claude (local sessions only).
wcd() {
  local dir
  dir="$(resume path "$@")" && cd "$dir"
}

alias r='resume'
alias rc='resume code'
alias rl='resume list'
