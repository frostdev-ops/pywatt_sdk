"""PyWatt CLI - Main command line interface

This module provides the main CLI commands for creating and managing PyWatt modules.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
import click
import jinja2
from datetime import datetime

from . import __version__
from .templates import get_template_content, AVAILABLE_TEMPLATES


@click.group()
@click.version_option(version=__version__, prog_name="pywatt-cli")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """PyWatt CLI - Tools for creating and managing PyWatt modules."""
    ctx.ensure_object(dict)


@cli.command()
@click.argument('module_name')
@click.option('--lib', is_flag=True, help='Create a library module instead of binary')
@click.option('--framework', 
              type=click.Choice(['fastapi', 'flask', 'starlette', 'none']), 
              default='fastapi',
              help='Web framework to use')
@click.option('--transport',
              type=click.Choice(['http', 'ipc', 'both']),
              default='both',
              help='Transport type to configure')
@click.option('--output-dir', '-o',
              type=click.Path(),
              help='Output directory (default: current directory)')
@click.option('--features',
              multiple=True,
              type=click.Choice(['database', 'cache', 'jwt', 'streaming', 'metrics']),
              help='Additional features to enable')
@click.option('--database',
              type=click.Choice(['postgresql', 'mysql', 'sqlite']),
              help='Database type to configure')
@click.option('--cache',
              type=click.Choice(['redis', 'memcached', 'memory']),
              help='Cache type to configure')
@click.option('--force', is_flag=True, help='Overwrite existing directory')
def new(
    module_name: str,
    lib: bool,
    framework: str,
    transport: str,
    output_dir: Optional[str],
    features: tuple,
    database: Optional[str],
    cache: Optional[str],
    force: bool,
) -> None:
    """Create a new PyWatt module project."""
    
    # Validate module name
    if not _is_valid_module_name(module_name):
        click.echo(f"Error: '{module_name}' is not a valid module name", err=True)
        click.echo("Module names should use kebab-case (e.g., 'my-module')", err=True)
        sys.exit(1)
    
    # Determine output directory
    if output_dir:
        project_dir = Path(output_dir) / module_name
    else:
        project_dir = Path.cwd() / module_name
    
    # Check if directory exists
    if project_dir.exists() and not force:
        click.echo(f"Error: Directory '{project_dir}' already exists", err=True)
        click.echo("Use --force to overwrite", err=True)
        sys.exit(1)
    
    # Create project directory
    if project_dir.exists() and force:
        shutil.rmtree(project_dir)
    
    project_dir.mkdir(parents=True, exist_ok=True)
    
    # Prepare template context
    context = _prepare_template_context(
        module_name=module_name,
        lib=lib,
        framework=framework,
        transport=transport,
        features=features,
        database=database,
        cache=cache,
    )
    
    # Generate project files
    try:
        _generate_project_files(project_dir, context)
        click.echo(f"✅ Created PyWatt module '{module_name}' in {project_dir}")
        
        # Print next steps
        _print_next_steps(module_name, project_dir, framework)
        
    except Exception as e:
        click.echo(f"Error creating project: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('shell', type=click.Choice(['bash', 'zsh', 'fish', 'powershell']))
def generate_completions(shell: str) -> None:
    """Generate shell completions for the CLI."""
    try:
        if shell == 'bash':
            completion = _get_bash_completion()
        elif shell == 'zsh':
            completion = _get_zsh_completion()
        elif shell == 'fish':
            completion = _get_fish_completion()
        elif shell == 'powershell':
            completion = _get_powershell_completion()
        else:
            click.echo(f"Unsupported shell: {shell}", err=True)
            sys.exit(1)
        
        click.echo(completion)
    except Exception as e:
        click.echo(f"Error generating completions: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('project_dir', type=click.Path(exists=True))
def validate(project_dir: str) -> None:
    """Validate a PyWatt module project structure."""
    project_path = Path(project_dir)
    
    click.echo(f"Validating PyWatt module at {project_path}")
    
    issues = []
    
    # Check for required files
    required_files = [
        'pyproject.toml',
        'README.md',
        '.gitignore',
    ]
    
    for file_name in required_files:
        file_path = project_path / file_name
        if not file_path.exists():
            issues.append(f"Missing required file: {file_name}")
    
    # Check for main module file
    main_files = ['main.py', 'app.py', '__main__.py']
    has_main = any((project_path / f).exists() for f in main_files)
    if not has_main:
        issues.append("No main module file found (main.py, app.py, or __main__.py)")
    
    # Check pyproject.toml structure
    pyproject_path = project_path / 'pyproject.toml'
    if pyproject_path.exists():
        try:
            import tomli
            with open(pyproject_path, 'rb') as f:
                pyproject_data = tomli.load(f)
            
            # Check for pywatt_sdk dependency
            deps = pyproject_data.get('project', {}).get('dependencies', [])
            has_pywatt = any('pywatt_sdk' in dep for dep in deps)
            if not has_pywatt:
                issues.append("pywatt_sdk dependency not found in pyproject.toml")
                
        except Exception as e:
            issues.append(f"Error reading pyproject.toml: {e}")
    
    # Check if project can be imported
    try:
        # Add project directory to Python path temporarily
        sys.path.insert(0, str(project_path))
        
        # Try to run basic validation
        result = subprocess.run(
            [sys.executable, '-m', 'py_compile'] + [str(f) for f in project_path.glob('*.py')],
            capture_output=True,
            text=True,
            cwd=project_path
        )
        
        if result.returncode != 0:
            issues.append(f"Python syntax errors found:\n{result.stderr}")
            
    except Exception as e:
        issues.append(f"Error validating Python files: {e}")
    finally:
        if str(project_path) in sys.path:
            sys.path.remove(str(project_path))
    
    # Report results
    if issues:
        click.echo("❌ Validation failed with the following issues:")
        for issue in issues:
            click.echo(f"  • {issue}")
        sys.exit(1)
    else:
        click.echo("✅ Project validation passed!")


@cli.command()
@click.option('--list-templates', is_flag=True, help='List available templates')
def templates(list_templates: bool) -> None:
    """Manage project templates."""
    if list_templates:
        click.echo("Available templates:")
        for template_name, description in AVAILABLE_TEMPLATES.items():
            click.echo(f"  {template_name}: {description}")
    else:
        click.echo("Use --list-templates to see available templates")


def _is_valid_module_name(name: str) -> bool:
    """Validate module name follows kebab-case convention."""
    import re
    return bool(re.match(r'^[a-z][a-z0-9-]*[a-z0-9]$', name)) and '--' not in name


def _prepare_template_context(
    module_name: str,
    lib: bool,
    framework: str,
    transport: str,
    features: tuple,
    database: Optional[str],
    cache: Optional[str],
) -> Dict[str, Any]:
    """Prepare template context for rendering."""
    
    # Convert kebab-case to snake_case for Python
    python_name = module_name.replace('-', '_')
    
    # Convert kebab-case to PascalCase for class names
    class_name = ''.join(word.capitalize() for word in module_name.split('-'))
    
    context = {
        'module_name': module_name,
        'python_name': python_name,
        'class_name': class_name,
        'is_lib': lib,
        'framework': framework,
        'transport': transport,
        'features': list(features),
        'database': database,
        'cache': cache,
        'year': datetime.now().year,
        'date': datetime.now().strftime('%Y-%m-%d'),
        
        # Feature flags
        'enable_database': 'database' in features or database is not None,
        'enable_cache': 'cache' in features or cache is not None,
        'enable_jwt': 'jwt' in features,
        'enable_streaming': 'streaming' in features,
        'enable_metrics': 'metrics' in features,
        'enable_http': transport in ('http', 'both'),
        'enable_ipc': transport in ('ipc', 'both'),
        
        # Framework-specific flags
        'use_fastapi': framework == 'fastapi',
        'use_flask': framework == 'flask',
        'use_starlette': framework == 'starlette',
        'use_none': framework == 'none',
    }
    
    return context


def _generate_project_files(project_dir: Path, context: Dict[str, Any]) -> None:
    """Generate all project files from templates."""
    
    # Setup Jinja2 environment
    env = jinja2.Environment(
        loader=jinja2.DictLoader({}),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    
    # Files to generate
    files_to_generate = [
        ('pyproject.toml', 'pyproject.toml.j2'),
        ('README.md', 'README.md.j2'),
        ('.gitignore', 'gitignore.j2'),
        ('main.py', f"main_{context['framework']}.py.j2"),
        ('requirements.txt', 'requirements.txt.j2'),
        ('Dockerfile', 'Dockerfile.j2'),
        ('docker-compose.yml', 'docker-compose.yml.j2'),
    ]
    
    # Add test files
    test_dir = project_dir / 'tests'
    test_dir.mkdir(exist_ok=True)
    files_to_generate.extend([
        ('tests/__init__.py', 'tests_init.py.j2'),
        ('tests/test_main.py', 'test_main.py.j2'),
        ('tests/conftest.py', 'conftest.py.j2'),
    ])
    
    # Add CI/CD files
    github_dir = project_dir / '.github' / 'workflows'
    github_dir.mkdir(parents=True, exist_ok=True)
    files_to_generate.append(
        ('.github/workflows/ci.yml', 'github_ci.yml.j2')
    )
    
    # Generate each file
    for output_path, template_name in files_to_generate:
        template_content = get_template_content(template_name)
        template = env.from_string(template_content)
        
        rendered_content = template.render(**context)
        
        output_file = project_dir / output_path
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(rendered_content)


def _print_next_steps(module_name: str, project_dir: Path, framework: str) -> None:
    """Print next steps for the user."""
    click.echo("\n📋 Next steps:")
    click.echo(f"  1. cd {project_dir}")
    click.echo("  2. pip install -e .")
    click.echo("  3. Set up your environment variables")
    
    if framework != 'none':
        click.echo("  4. Run your module:")
        click.echo("     python main.py")
    
    click.echo("\n📚 Documentation:")
    click.echo("  • PyWatt SDK docs: https://docs.pywatt.io")
    click.echo("  • Examples: https://github.com/pywatt/examples")
    
    click.echo(f"\n🎉 Happy coding with PyWatt!")


def _get_bash_completion() -> str:
    """Generate bash completion script."""
    return '''
_pywatt_cli_completion() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    case ${COMP_CWORD} in
        1)
            opts="new generate-completions validate templates"
            COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
            return 0
            ;;
        2)
            case "${prev}" in
                new)
                    # Complete module names (no specific completion)
                    return 0
                    ;;
                generate-completions)
                    opts="bash zsh fish powershell"
                    COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
                    return 0
                    ;;
                validate)
                    # Complete directories
                    COMPREPLY=( $(compgen -d -- ${cur}) )
                    return 0
                    ;;
            esac
            ;;
    esac
}

complete -F _pywatt_cli_completion pywatt-cli
'''


def _get_zsh_completion() -> str:
    """Generate zsh completion script."""
    return '''
#compdef pywatt-cli

_pywatt_cli() {
    local context state line
    
    _arguments -C \
        '1: :->command' \
        '*: :->args'
    
    case $state in
        command)
            _values 'commands' \
                'new[Create a new PyWatt module]' \
                'generate-completions[Generate shell completions]' \
                'validate[Validate project structure]' \
                'templates[Manage templates]'
            ;;
        args)
            case $words[2] in
                new)
                    _arguments \
                        '--lib[Create library module]' \
                        '--framework[Web framework]:framework:(fastapi flask starlette none)' \
                        '--transport[Transport type]:transport:(http ipc both)' \
                        '--output-dir[Output directory]:directory:_directories' \
                        '--force[Overwrite existing]'
                    ;;
                generate-completions)
                    _values 'shells' bash zsh fish powershell
                    ;;
                validate)
                    _directories
                    ;;
            esac
            ;;
    esac
}

_pywatt_cli "$@"
'''


def _get_fish_completion() -> str:
    """Generate fish completion script."""
    return '''
# Fish completion for pywatt-cli

complete -c pywatt-cli -n "__fish_use_subcommand" -a "new" -d "Create a new PyWatt module"
complete -c pywatt-cli -n "__fish_use_subcommand" -a "generate-completions" -d "Generate shell completions"
complete -c pywatt-cli -n "__fish_use_subcommand" -a "validate" -d "Validate project structure"
complete -c pywatt-cli -n "__fish_use_subcommand" -a "templates" -d "Manage templates"

# new command options
complete -c pywatt-cli -n "__fish_seen_subcommand_from new" -l lib -d "Create library module"
complete -c pywatt-cli -n "__fish_seen_subcommand_from new" -l framework -a "fastapi flask starlette none" -d "Web framework"
complete -c pywatt-cli -n "__fish_seen_subcommand_from new" -l transport -a "http ipc both" -d "Transport type"
complete -c pywatt-cli -n "__fish_seen_subcommand_from new" -l output-dir -d "Output directory"
complete -c pywatt-cli -n "__fish_seen_subcommand_from new" -l force -d "Overwrite existing"

# generate-completions options
complete -c pywatt-cli -n "__fish_seen_subcommand_from generate-completions" -a "bash zsh fish powershell"
'''


def _get_powershell_completion() -> str:
    """Generate PowerShell completion script."""
    return '''
Register-ArgumentCompleter -Native -CommandName pywatt-cli -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    
    $commands = @('new', 'generate-completions', 'validate', 'templates')
    $shells = @('bash', 'zsh', 'fish', 'powershell')
    $frameworks = @('fastapi', 'flask', 'starlette', 'none')
    $transports = @('http', 'ipc', 'both')
    
    $tokens = $commandAst.CommandElements
    
    if ($tokens.Count -eq 2) {
        $commands | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
            [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
        }
    }
    elseif ($tokens.Count -eq 3) {
        switch ($tokens[1].Value) {
            'generate-completions' {
                $shells | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
                    [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
                }
            }
        }
    }
}
'''


if __name__ == '__main__':
    cli() 