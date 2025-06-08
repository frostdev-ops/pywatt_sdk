"""PyWatt SDK command-line interface.

This module provides the CLI for PyWatt SDK, allowing users to create new modules
from templates, generate shell completions, and perform other helpful tasks.
"""

import os
import sys
import argparse
import logging
from typing import List, Optional, Dict, Any
import shutil

from .template_manager import TemplateManager

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Set up logging for the CLI.
    
    Args:
        verbose: If True, enable debug logging
    """
    logging_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=logging_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def create_module_command(args: argparse.Namespace) -> int:
    """Create a new module from a template.
    
    Args:
        args: Command line arguments
        
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    try:
        # Create template manager
        template_manager = TemplateManager()
        
        # Set up variables
        variables = {
            "MODULE_VERSION": args.version,
            "MODULE_DESCRIPTION": args.description,
        }
        
        # Get template name
        template_name = f"template_{args.template}"
        
        # Create the module
        output_path = os.path.abspath(args.output) if args.output else os.getcwd()
        module_dir = template_manager.create_module(
            name=args.name,
            output_dir=output_path,
            template_name=template_name,
            variables=variables
        )
        
        print(f"Successfully created module '{args.name}' at {module_dir}")
        
        # Display next steps
        print("\nNext steps:")
        print(f"  cd {module_dir}")
        if os.path.exists(os.path.join(module_dir, "requirements.txt")):
            print("  pip install -r requirements.txt")
        print("  python main.py")
        
        return 0
    except Exception as e:
        logger.error(f"Failed to create module: {e}")
        if args.verbose:
            logger.exception("Detailed error")
        return 1


def list_templates_command(args: argparse.Namespace) -> int:
    """List available module templates.
    
    Args:
        args: Command line arguments
        
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    try:
        # Create template manager
        template_manager = TemplateManager()
        
        # List templates
        templates = template_manager.list_templates()
        
        print("Available templates:")
        for template in templates:
            # Remove template_ prefix for display
            display_name = template.replace("template_", "")
            template_dir = os.path.join(template_manager.templates_dir, template)
            
            # Try to get description from README.md if it exists
            description = ""
            readme_path = os.path.join(template_dir, "README.md")
            if os.path.exists(readme_path):
                with open(readme_path, "r") as f:
                    first_line = f.readline().strip()
                    if first_line.startswith("# "):
                        description = first_line[2:]
            
            print(f"  {display_name:<15} - {description}")
        
        return 0
    except Exception as e:
        logger.error(f"Failed to list templates: {e}")
        if args.verbose:
            logger.exception("Detailed error")
        return 1


def generate_completions_command(args: argparse.Namespace) -> int:
    """Generate shell completions for the CLI.
    
    Args:
        args: Command line arguments
        
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    try:
        shell = args.shell.lower()
        
        # Handle different shell types
        if shell == "bash":
            generate_bash_completions()
        elif shell == "zsh":
            generate_zsh_completions()
        elif shell == "fish":
            generate_fish_completions()
        else:
            print(f"Unsupported shell: {shell}")
            return 1
        
        return 0
    except Exception as e:
        logger.error(f"Failed to generate completions: {e}")
        if args.verbose:
            logger.exception("Detailed error")
        return 1


def generate_bash_completions() -> None:
    """Generate Bash completions."""
    completions = """
# PyWatt SDK bash completion script
_pywatt_completion() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    # Top-level commands
    if [[ ${COMP_CWORD} -eq 1 ]]; then
        opts="new list-templates generate-completions help"
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
        return 0
    fi
    
    # Subcommand options
    case "${COMP_WORDS[1]}" in
        new)
            case "${prev}" in
                -t|--template)
                    # Get list of available templates
                    local templates=$(pywatt list-templates | grep -v "Available" | awk '{print $1}')
                    COMPREPLY=( $(compgen -W "${templates}" -- ${cur}) )
                    ;;
                -o|--output)
                    # Directory completion
                    COMPREPLY=( $(compgen -d -- ${cur}) )
                    ;;
                *)
                    opts="-t --template -o --output -v --verbose --version --description"
                    COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
                    ;;
            esac
            ;;
        generate-completions)
            if [[ ${prev} == "generate-completions" ]]; then
                opts="bash zsh fish"
                COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
            fi
            ;;
    esac
    
    return 0
}

complete -F _pywatt_completion pywatt
"""
    print(completions)


def generate_zsh_completions() -> None:
    """Generate Zsh completions."""
    completions = """
#compdef pywatt

_pywatt() {
    local -a commands
    commands=(
        'new:Create a new module'
        'list-templates:List available templates'
        'generate-completions:Generate shell completions'
        'help:Show help information'
    )
    
    _arguments -C \\
        '1: :->command' \\
        '*:: :->args' && ret=0
        
    case $state in
        command)
            _describe -t commands 'pywatt commands' commands && ret=0
            ;;
        args)
            case $line[1] in
                new)
                    _arguments \\
                        '(-t --template)'{-t,--template}'[Template to use]:template:_pywatt_templates' \\
                        '(-o --output)'{-o,--output}'[Output directory]:directory:_files -/' \\
                        '(-v --verbose)'{-v,--verbose}'[Enable verbose output]' \\
                        '--version[Module version]' \\
                        '--description[Module description]' \\
                        '1:module name' && ret=0
                    ;;
                generate-completions)
                    _arguments '1:shell:(bash zsh fish)' && ret=0
                    ;;
            esac
            ;;
    esac
    
    return ret
}

_pywatt_templates() {
    local -a templates
    # Get list of available templates
    templates=($(pywatt list-templates | grep -v "Available" | awk '{print $1}'))
    _describe -t templates 'templates' templates
}

_pywatt
"""
    print(completions)


def generate_fish_completions() -> None:
    """Generate Fish completions."""
    completions = """
# Fish completions for PyWatt SDK

# Main commands
complete -c pywatt -f -n "__fish_use_subcommand" -a new -d "Create a new module"
complete -c pywatt -f -n "__fish_use_subcommand" -a list-templates -d "List available templates"
complete -c pywatt -f -n "__fish_use_subcommand" -a generate-completions -d "Generate shell completions"
complete -c pywatt -f -n "__fish_use_subcommand" -a help -d "Show help information"

# 'new' command options
complete -c pywatt -f -n "__fish_seen_subcommand_from new" -s t -l template -d "Template to use"
complete -c pywatt -f -n "__fish_seen_subcommand_from new" -s o -l output -d "Output directory" -a "(__fish_complete_directories)"
complete -c pywatt -f -n "__fish_seen_subcommand_from new" -s v -l verbose -d "Enable verbose output"
complete -c pywatt -f -n "__fish_seen_subcommand_from new" -l version -d "Module version"
complete -c pywatt -f -n "__fish_seen_subcommand_from new" -l description -d "Module description"

# 'generate-completions' command options
complete -c pywatt -f -n "__fish_seen_subcommand_from generate-completions" -a "bash zsh fish" -d "Shell type"

# Template completion
function __pywatt_templates
    # Extract template names
    pywatt list-templates | grep -v "Available" | awk '{print $1}'
end

complete -c pywatt -f -n "__fish_seen_subcommand_from new; and __fish_contains_opt -s t template" -a "(__pywatt_templates)"
"""
    print(completions)


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for the CLI.
    
    Args:
        args: Command line arguments
        
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Create the main parser
    parser = argparse.ArgumentParser(
        prog="pywatt",
        description="PyWatt SDK command-line interface",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    # Create subparsers
    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        help="Command to execute"
    )
    
    # Create module command
    new_parser = subparsers.add_parser(
        "new",
        help="Create a new module"
    )
    new_parser.add_argument(
        "name",
        help="Name of the module"
    )
    new_parser.add_argument(
        "-t", "--template",
        default="basic",
        help="Template to use"
    )
    new_parser.add_argument(
        "-o", "--output",
        help="Output directory"
    )
    new_parser.add_argument(
        "--version",
        default="0.1.0",
        help="Module version"
    )
    new_parser.add_argument(
        "--description",
        default=None,
        help="Module description"
    )
    
    # List templates command
    list_parser = subparsers.add_parser(
        "list-templates",
        help="List available templates"
    )
    
    # Generate completions command
    completions_parser = subparsers.add_parser(
        "generate-completions",
        help="Generate shell completions"
    )
    completions_parser.add_argument(
        "shell",
        choices=["bash", "zsh", "fish"],
        help="Shell to generate completions for"
    )
    
    # Parse arguments
    args = parser.parse_args(args)
    
    # Set up logging
    setup_logging(args.verbose)
    
    # Execute the appropriate command
    if args.command == "new":
        return create_module_command(args)
    elif args.command == "list-templates":
        return list_templates_command(args)
    elif args.command == "generate-completions":
        return generate_completions_command(args)
    else:
        # No command or help
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
