# Contributing

## Setup

### Prerequisites

- **[Lefthook](https://github.com/evilmartians/lefthook)** (Git hooks)
- **[ShellCheck](https://github.com/koalaman/shellcheck)** (Shell linting)
- **[dprint](https://dprint.dev/)** (Markdown/JSON formatting)
- **[Direnv](https://direnv.net/)** (Optional automation)

### Installation

1. **Install Hooks:**
   ```bash
   lefthook install
   ```
   _Or use `direnv allow` to auto-install via `.envrc`._

2. **Verify:**
   ```bash
   lefthook run pre-commit
   ```
