# yessir

`yessir` presses Enter on recognized Claude Code approval prompts in one tmux pane.
Use it with Claude Code in Manual mode.
The helper accepts the plain **Yes** option when that option is selected.
It does not change the permission mode.

> [!WARNING]
> **USE AT YOUR OWN RISK.** The helper approves commands and file changes without your review.
> It does not check whether an action is safe.
> An approved action can delete data or cause other damage.
> Read the [disclaimer](#disclaimer) before use.

## Requirements

- Linux with a readable `/proc` filesystem.
- Python 3.8 or later. No extra Python packages are required.
- tmux.
- Claude Code with an active terminal chat.
- Bash to run the installer.
- `curl` and `tar` to install from GitHub.

Tests ran with tmux 3.2a and simulated Claude Code approval prompts.
The prompt rules were prepared for Claude Code 2.1.285.
The tests do not send requests to a model.
Other Claude Code versions can use different prompt text.
macOS and native Windows are not supported.
WSL requires a Linux installation of the tools.

## Install

Run this command as your user. Do not use `sudo`.

```sh
curl -fsSL https://raw.githubusercontent.com/gsiros/yessir/main/install.sh | bash
```

The installer writes these files:

```text
~/.local/bin/yessir
~/.local/bin/claude-tmux-yes
~/.local/share/yessir/LICENSE
```

The installer does not start the helper.
It does not change shell or tmux settings.
It uses HTTPS to download the source from GitHub.
It replaces existing files at the three installation paths.

If `~/.local/bin` is absent from `PATH`, add this line to your shell startup file:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Use `~/.bashrc` for Bash or `~/.zshrc` for Zsh.
Then open a new shell.
Check the command:

```sh
yessir --help
```

### Install from a local checkout

```sh
git clone https://github.com/gsiros/yessir.git
cd yessir
bash install.sh
```

This procedure uses the files in the checkout. It does not download an archive.

### Use a different installation path

```sh
bash install.sh --prefix "$HOME/tools/yessir"
```

This command installs the scripts in `$HOME/tools/yessir/bin`.
It installs the license in `$HOME/tools/yessir/share/yessir`.
Add the new `bin` directory to `PATH`.
Keep both scripts in the same directory.

### Select a branch, tag, or commit

Use `--ref` to select the source archive:

```sh
curl -fsSL https://raw.githubusercontent.com/gsiros/yessir/main/install.sh \
  | bash -s -- --ref COMMIT_SHA
```

Replace `COMMIT_SHA` with a commit ID, branch name, or tag name.
This command still uses the installer from `main`.
To select the installer version too, replace `main` in the URL with the same reference.

## Use

1. Open tmux.
2. Start `claude` in the pane that you want to control.
3. Start a chat in Manual mode.
4. Open the tmux command prompt inside the window.
   Hold **Ctrl** and press **b**. Release both keys, then press **:**.
   The command prompt appears at the bottom of the tmux window.
   **Ctrl-b** is the default tmux prefix. Use your configured prefix if you changed it.
5. Enter this tmux command:

   ```tmux
   run-shell 'yessir --on'
   ```

6. Press **Enter** to run the command.
7. If tmux opens a view of the command output (stdout), press **q** to close it.
   You return to the Claude chat in the same pane.
   Closing the output view does not turn the helper off.

Use the same procedure for the commands below.
Press **q** after each command if its output view remains open.

To stop the helper, open the tmux command prompt again:

```tmux
run-shell 'yessir --off'
```

To read its state:

```tmux
run-shell 'yessir --status'
```

To toggle it:

```tmux
run-shell 'yessir'
```

The command finds the current pane. You do not need to enter its ID.
The helper controls only that pane.
It remains enabled if you select another pane.
It stops when the selected Claude process exits.
Enable it again after you start a new Claude session.

Do not type `yessir --on` into the Claude chat input.
Use the tmux command prompt to run the command while Claude has the terminal.
If tmux cannot find `yessir`, use the installed path:

```tmux
run-shell '~/.local/bin/yessir --on'
```

### Optional key binding

Add this line to `~/.tmux.conf`:

```tmux
bind-key y run-shell '~/.local/bin/claude-tmux-yes toggle --pane #{pane_id}'
```

Use the actual helper path if you installed it in a different directory.
Reload the file from the tmux command prompt:

```tmux
source-file ~/.tmux.conf
```

Press the tmux prefix, then **y**, to toggle the helper in the current pane.
This binding replaces an existing prefix-plus-y binding.

## Operation

`yessir` is a shell script. It starts the Python helper beside it.
The helper checks the pane and its foreground process through tmux and Linux `/proc`.
It then starts a background watcher for that Claude process.

The watcher reads the visible pane text with `tmux capture-pane` every 0.15 seconds.
It looks for these items together:

- A recognized command or file approval question.
- A selected option whose text is exactly `Yes`.
- A `No` option below it.
- An `Esc to cancel` or `Esc to reject` footer at the bottom.

The screen must remain unchanged for at least 0.3 seconds.
The watcher checks the screen and process again before it sends Enter.
It remembers the last accepted screen to prevent repeated Enter keys on an unchanged dialog.

The watcher pauses during tmux copy mode.
It also pauses if Claude is suspended or loses control of the terminal.
Turning the helper off removes its flag from the pane.
The watcher then stops at its next check.

The helper has no network code.
It does not save the captured pane text.
The installer uses the network only when it downloads the source.
The helper stores lock files in `~/.cache/claude-tmux-yes`.

## Limits

Detection depends on terminal text. It does not use a Claude approval API.
It cannot confirm that matching text is an actual permission dialog.
Matching text can produce an incorrect approval.
New wording, a different language, or a different screen layout can prevent detection.

The helper does not move the selection to **Yes**.
It does not accept **Yes, and switch to auto mode** or **Yes, and do not ask again**.
It does not approve an unrecognized prompt.
Two identical prompts can be missed if no visible change occurs between them.

The screen check and the Enter key are separate operations.
The screen can change between them.
There is no guarantee that Enter reaches the intended dialog.

`ON` reports a stored tmux flag. It is not a complete check of the watcher.
Watcher errors are not logged.
The helper checks the Claude process, but it does not verify the permission mode.
Keep Claude in Manual mode yourself.

## Troubleshooting

| Problem | Action |
| --- | --- |
| tmux cannot find `yessir` | Use `~/.local/bin/yessir` in `run-shell`, or correct the tmux server's `PATH`. |
| The helper says to start Claude first | Select the Claude pane. Make sure Claude is running in the foreground. |
| The state is ON, but a prompt remains | Check that plain **Yes** is selected. Check the prompt text and footer. |
| Approvals stop in copy mode | Exit copy mode. |
| Approvals stop after a Claude restart | Enable the helper again. |
| ON remains after a watcher failure | Run `--off`, then `--on`. |

To list pane IDs, run this command from a shell:

```sh
tmux list-panes -a -F '#{pane_id} #{pane_current_command}'
```

To read a pane's text, run:

```sh
tmux capture-pane -p -t %3
```

Replace `%3` with the affected pane ID.
Remove private data before you include captured text in a bug report.
The prompt rules are at the top of `bin/claude-tmux-yes`.

To control a specific pane from another shell, use the helper directly:

```sh
claude-tmux-yes on --pane %3
claude-tmux-yes off --pane %3
```

For a different tmux server, also supply `--socket /path/to/tmux.sock`.

## Update and remove

Before an update, turn the helper off in each pane where it is enabled.
Then run the installation command again.
Enable the helper again after the update.

Before removal, turn the helper off in each affected pane.
For the default installation, remove these files:

```sh
rm -- "$HOME/.local/bin/yessir" "$HOME/.local/bin/claude-tmux-yes" \
  "$HOME/.local/share/yessir/LICENSE"
```

Remove the optional key binding from `~/.tmux.conf` if you added it.
Adjust the paths if you used `--prefix`.
The cache contains only lock files. You can remove it when all watchers have stopped.

## Tests

From a checkout, run:

```sh
python3 -m unittest discover -s tests -v
```

The tests check prompt detection, Enter keys, copy mode, and watcher shutdown.
They also check local installation and downloaded installation.
They use temporary directories and an isolated tmux server.
The download tests use a local archive. They do not contact GitHub.

To check shell scripts, use ShellCheck:

```sh
shellcheck install.sh bin/yessir
```

## Disclaimer

**USE AT YOUR OWN RISK.**

To the maximum extent permitted by law, the author, gsiros, accepts **NO RESPONSIBILITY** for damage caused by this software.
The contributors also accept no responsibility for such damage.
This includes data loss, unwanted file changes, security failures, service failures, and financial loss.
You are responsible for all actions that the helper approves and all effects of those actions.

The software is provided **AS IS**, without any warranty.
There is no guarantee of correct prompt detection, correct approval, or safe operation.
The author and contributors are not liable for direct, indirect, incidental, special, or consequential damages, subject to applicable law.

This project is not affiliated with Anthropic or the tmux project.

## License

Apache License 2.0. See [LICENSE](LICENSE), including Sections 7 and 8.
