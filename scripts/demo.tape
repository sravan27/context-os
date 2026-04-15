# Context OS demo — record with `vhs scripts/demo.tape` to produce demo.gif
# https://github.com/charmbracelet/vhs

Output demo.gif

Set FontSize 16
Set Width 1100
Set Height 650
Set Theme "Dracula"
Set TypingSpeed 40ms
Set PlaybackSpeed 1.2

Type "# Context OS: every proven Claude Code optimization in one command"
Sleep 800ms
Enter

Type "# first, see what you'd save (no install required):"
Enter
Sleep 400ms

Type "curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --measure"
Enter
Sleep 4s

Type "# credible? run the install:"
Enter
Sleep 400ms

Type "curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash"
Enter
Sleep 6s

Type "# check what's active:"
Enter
Sleep 400ms

Type "curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --status"
Enter
Sleep 4s

Type "# start a new Claude Code session — you're saving tokens on every turn"
Sleep 2s
Enter
