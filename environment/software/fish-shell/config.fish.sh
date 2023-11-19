if status is-interactive
    # Commands to run in interactive sessions can go here
end

function fish_remove_path
  if set -l index (contains -i "$argv" $fish_user_paths)
    set -e fish_user_paths[$index]
    echo "Removed $argv from the path"
  end
end

source $HOME/.asdf/asdf.fish

export DOTNET_CLI_TELEMETRY_OPTOUT=1

export GOROOT=/usr/local/go-1.21
export GOPATH=$HOME/projects/go
export GOBIN=$GOPATH/bin

export MODULAR_HOME=$HOME/.modular

fish_add_path $GOROOT/bin
fish_add_path $HOME/projects/go/bin
fish_add_path $HOME/.modular/pkg/packages.modular.com_mojo/bin


set -Ux PYENV_ROOT $HOME/.pyenv
fish_add_path $PYENV_ROOT/bin

pyenv init - | source
