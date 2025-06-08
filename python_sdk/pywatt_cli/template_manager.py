"""Module template management for PyWatt CLI.

This module provides functionality for creating new module templates
from predefined templates, with variable substitution and customization.
"""

import os
import shutil
import re
from typing import Dict, Any, Optional, List


class TemplateManager:
    """Manager for module templates.
    
    This class provides functionality for creating new module templates
    from predefined templates, with variable substitution and customization.
    """

    def __init__(self, templates_dir: Optional[str] = None) -> None:
        """Initialize a template manager.
        
        Args:
            templates_dir: Optional directory containing templates
        """
        if templates_dir is None:
            # Use default templates directory
            self.templates_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), 
                "templates"
            )
        else:
            self.templates_dir = templates_dir
            
        # Ensure templates directory exists
        if not os.path.exists(self.templates_dir):
            os.makedirs(self.templates_dir)
    
    def list_templates(self) -> List[str]:
        """List available templates.
        
        Returns:
            List of template names
        """
        return [d for d in os.listdir(self.templates_dir) 
                if os.path.isdir(os.path.join(self.templates_dir, d)) and 
                   d.startswith("template_")]
    
    def create_module(
        self, 
        name: str, 
        output_dir: str, 
        template_name: str = "template_basic", 
        variables: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a new module from a template.
        
        Args:
            name: Name of the module
            output_dir: Directory to create the module in
            template_name: Name of the template to use
            variables: Optional dictionary of variables to substitute
            
        Returns:
            Path to the created module directory
            
        Raises:
            FileNotFoundError: If template does not exist
            ValueError: If name is invalid
        """
        # Validate module name
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]+$', name):
            raise ValueError(
                "Module name must start with a letter and contain only letters, "
                "numbers, underscores, and hyphens"
            )
        
        # Set up variables for substitution
        if variables is None:
            variables = {}
            
        # Add default variables
        variables.update({
            "MODULE_NAME": name,
            "MODULE_VERSION": variables.get("MODULE_VERSION", "0.1.0"),
            "MODULE_DESCRIPTION": variables.get(
                "MODULE_DESCRIPTION", 
                f"PyWatt module: {name}"
            ),
            "MODULE_AUTHOR": variables.get("MODULE_AUTHOR", ""),
        })
        
        # Get template path
        template_path = os.path.join(self.templates_dir, template_name)
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template '{template_name}' not found")
            
        # Create output directory
        module_dir = os.path.join(output_dir, name)
        if not os.path.exists(module_dir):
            os.makedirs(module_dir)
        
        # Copy and process template files
        for root, dirs, files in os.walk(template_path):
            # Get relative path from template root
            rel_path = os.path.relpath(root, template_path)
            target_dir = os.path.join(module_dir, rel_path) if rel_path != '.' else module_dir
            
            # Create target directory
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            
            # Process files
            for file in files:
                source_file = os.path.join(root, file)
                # Process the filename for variables
                target_file_name = self._substitute_variables(file, variables)
                target_file = os.path.join(target_dir, target_file_name)
                
                # Process text files
                if self._is_text_file(source_file):
                    with open(source_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Substitute variables in content
                    content = self._substitute_variables(content, variables)
                    
                    # Write processed content
                    with open(target_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                else:
                    # Copy binary files as-is
                    shutil.copy2(source_file, target_file)
        
        return module_dir
    
    def _is_text_file(self, file_path: str) -> bool:
        """Check if a file is a text file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if the file is a text file, False otherwise
        """
        # List of common text file extensions
        text_extensions = {
            '.py', '.md', '.txt', '.yaml', '.yml', '.json',
            '.toml', '.ini', '.cfg', '.html', '.css', '.js',
            '.sh', '.bat', '.ps1', '.dockerfile', '.env'
        }
        
        # Check extension
        _, ext = os.path.splitext(file_path)
        if ext.lower() in text_extensions:
            return True
            
        # Try to read as text
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                f.read(4096)  # Read a chunk to check if it's text
            return True
        except UnicodeDecodeError:
            return False
    
    def _substitute_variables(self, text: str, variables: Dict[str, Any]) -> str:
        """Substitute variables in a string.
        
        Args:
            text: Text to process
            variables: Dictionary of variable substitutions
            
        Returns:
            Processed text with variables substituted
        """
        result = text
        # Handle both {{VAR}} and {{VAR|default}} syntax
        pattern = r'{{([A-Za-z0-9_]+)(\|[^}]+)?}}'
        
        def replace_match(match):
            var_name = match.group(1)
            default_value = None
            
            # Check if default value is provided
            if match.group(2):
                default_value = match.group(2)[1:]  # Remove the | character
                
            # Get the value
            value = variables.get(var_name, default_value)
            if value is None:
                return f"{{{{{var_name}}}}}"  # Leave unchanged if no value/default
            
            return str(value)
        
        # Replace all matches
        result = re.sub(pattern, replace_match, result)
        return result
