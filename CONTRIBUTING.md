# Contributing

## Setup

### Prerequisites

- **[Lefthook](https://github.com/evilmartians/lefthook)** (Git hooks)
- **[ShellCheck](https://github.com/koalaman/shellcheck)** (Linting)
- **[Direnv](https://direnv.net/)** (Optional automation)

### Installation

1.  **Install Hooks:**
    ```bash
    lefthook install
    ```
    *Or use `direnv allow` to auto-install via `.envrc`.*

2.  **Verify:**
    ```bash
    lefthook run pre-commit
    ```
