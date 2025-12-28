# Troubleshooting Neovim: Avante & Copilot Authentication

## The "Boot Loop" Issue

When setting up **Avante.nvim** with **GitHub Copilot** as the provider, you may
encounter a "Boot Loop" crash on startup if Copilot is not yet authenticated.

### Symptoms

- Neovim opens and immediately displays an error stack trace from `avante.nvim`.
- The error message says:
  `You must setup copilot with either copilot.lua or copilot.vim` or fails to
  get an OAuth token.
- You cannot run `:Copilot auth` because Neovim crashes or is blocked by the
  error before you can type.

### The Fix

To break this loop, you must temporarily disable Avante, authenticate Copilot,
and then re-enable Avante.

#### 1. Disable Avante

Edit your `dotfiles/nvim/.config/nvim/lua/plugins/avante.lua` and set
`enabled = false`:

```lua
return {
  {
    'yetone/avante.nvim',
    enabled = false, -- <--- Add this
    event = 'VeryLazy',
    -- ...
  }
}
```

#### 2. Authenticate Copilot

Open Neovim (it should now open without crashing).

1. Run `:Copilot status` to confirm it is not authenticated.
2. Run `:Copilot auth`.
3. Copy the 8-character code provided.
4. Open the GitHub URL (usually `https://github.com/login/device`) in your
   browser.
5. Paste the code and authorize.
6. Wait for the success message in Neovim.

#### 3. Re-enable Avante

Remove `enabled = false` from your `avante.lua` configuration.

```lua
return {
  {
    'yetone/avante.nvim',
    -- enabled = false, -- <--- Remove this
    event = 'VeryLazy',
    -- ...
  }
}
```

Restart Neovim. Avante should now load correctly using your cached Copilot
credentials.
