# Avoid Running Long Scripts Directly in the Terminal

**Do not run long-running scripts directly in the terminal.** This can cause issues with the Pty Host (Pseudo Terminal Host), such as terminal freezes, disconnections, or resource exhaustion.

## Why?

- **Pty Host Limitations:** The terminal's Pty Host is not designed to handle long-running or resource-intensive processes. Running such scripts can lead to instability or crashes.
- **Interruptions:** If your terminal session is interrupted (e.g., by closing the terminal or losing connection), your script will be terminated.
- **Resource Management:** Long scripts can consume significant resources, affecting other processes or users.

## Recommended Alternatives

- **Run Scripts in the Background:**  
  Use `nohup`, `&`, or `disown` to run scripts independently of the terminal session.
