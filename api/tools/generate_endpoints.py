#!/usr/bin/env python3
"""
Minimal API endpoint generator from OpenAPI specs.
Based on user's draft with improvements for dependency injection.
"""

import argparse
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

import yaml
import jinja2


def _model_from_request(operation: Dict[str, Any]) -> Optional[str]:
    """Extract request model from operation."""
    if "requestBody" not in operation:
        return None
    
    content = operation["requestBody"].get("content", {})
    json_content = content.get("application/json", {})
    schema = json_content.get("schema", {})
    
    if "$ref" in schema:
        model_name = schema["$ref"].split("/")[-1]
        # For POST/PUT operations, prefer Create/Update models if they exist
        # For now, return the base model - this can be enhanced later
        return model_name
    
    return None


def _model_from_response(operation: Dict[str, Any]) -> Optional[str]:
    """Extract response model from operation."""
    responses = operation.get("responses", {})
    success_response = responses.get("200") or responses.get("201")
    
    if not success_response:
        return None
    
    content = success_response.get("content", {})
    json_content = content.get("application/json", {})
    schema = json_content.get("schema", {})
    
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    
    # Handle array responses
    if schema.get("type") == "object" and "properties" in schema:
        # Look for array properties that might be the main response
        for prop_name, prop_schema in schema["properties"].items():
            if prop_schema.get("type") == "array":
                items = prop_schema.get("items", {})
                if "$ref" in items:
                    # Use wrapper response model name (e.g., SourcesResponse)
                    base_model = items['$ref'].split('/')[-1]
                    return f"{base_model}sResponse"
    
    return None


def _extract_path_params(path: str, operation: Dict[str, Any]) -> list:
    """Extract path parameters from operation."""
    params = []
    for param in operation.get("parameters", []):
        if param.get("in") == "path":
            param_type = "str"  # Default to string
            if "schema" in param:
                schema_type = param["schema"].get("type", "string")
                if schema_type == "integer":
                    param_type = "int"
                elif schema_type == "boolean":
                    param_type = "bool"
            
            params.append({
                "name": _snake_case(param["name"]),  # Convert to snake_case
                "original_name": param["name"],      # Keep original for path matching
                "type": param_type,
                "description": param.get("description", "")
            })
    
    return params


def _snake_case(text: str) -> str:
    """Convert camelCase to snake_case."""
    import re
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', text)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def generate_schemas(spec_path: str, service_name: str, services_root: str = "../../services") -> str:
    """Generate Pydantic schemas from OpenAPI spec using datamodel-codegen."""
    
    # Determine the target schema file path
    schema_dir = Path(services_root) / service_name / "src" / "schemas"
    schema_file = schema_dir / f"{service_name}.py"
    
    # Create schema directory if it doesn't exist
    schema_dir.mkdir(parents=True, exist_ok=True)
    
    # Run datamodel-codegen to generate schemas with additional response models
    cmd = [
        "datamodel-codegen",
        "--input", spec_path,
        "--output", str(schema_file),
        "--input-file-type", "openapi",
        "--output-model-type", "pydantic_v2.BaseModel",
        "--field-constraints",
        "--use-title-as-name",
        "--target-python-version", "3.13",
        "--openapi-scopes", "schemas",  # Only generate from schemas, not paths
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Add custom response models for inline response schemas
        _add_custom_response_models(spec_path, schema_file)
        
        print(f"Generated schemas written to: {schema_file}")
        return str(schema_file)
    except subprocess.CalledProcessError as e:
        print(f"Error generating schemas: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        raise
    except FileNotFoundError:
        print("Error: datamodel-codegen not found. Please install it: pip install datamodel-codegen")
        raise


def _add_custom_response_models(spec_path: str, schema_file: Path) -> None:
    """Add custom response models for inline response schemas that datamodel-codegen misses."""
    
    # Load OpenAPI spec
    spec_content = Path(spec_path).read_text()
    spec = yaml.safe_load(spec_content)
    
    # Find inline response schemas that need wrapper models
    response_models = []
    
    for path, path_item in spec.get("paths", {}).items():
        for verb, operation in path_item.items():
            if verb in ["get", "post", "put", "delete", "patch"]:
                responses = operation.get("responses", {})
                success_response = responses.get("200") or responses.get("201")
                
                if success_response:
                    content = success_response.get("content", {})
                    json_content = content.get("application/json", {})
                    schema = json_content.get("schema", {})
                    
                    # Check for object with array property (like SourcesResponse)
                    if (schema.get("type") == "object" and 
                        "properties" in schema and 
                        "$ref" not in schema):  # Inline schema
                        
                        for prop_name, prop_schema in schema["properties"].items():
                            if prop_schema.get("type") == "array":
                                items = prop_schema.get("items", {})
                                if "$ref" in items:
                                    base_model = items['$ref'].split('/')[-1]
                                    response_model_name = f"{base_model}sResponse"
                                    
                                    response_model = f"""
class {response_model_name}(BaseModel):
    {prop_name}: List[{base_model}] = Field(..., description='{prop_schema.get("description", f"List of {base_model.lower()} objects")}')"""
                                    
                                    if response_model not in response_models:
                                        response_models.append(response_model)
    
    # Append response models to the generated schema file if any were found
    if response_models:
        schema_content = schema_file.read_text()
        
        # Add List import if not present
        if "from typing import List" not in schema_content and "List" not in schema_content:
            schema_content = schema_content.replace(
                "from pydantic import BaseModel, Field",
                "from typing import List\n\nfrom pydantic import BaseModel, Field"
            )
        
        # Add the response models
        schema_content += "\n\n# Response wrapper models\n" + "\n".join(response_models)
        
        schema_file.write_text(schema_content)


def generate_endpoints(spec_path: str, output_path: str, service_name: str, generate_schemas_flag: bool = True) -> None:
    """Generate FastAPI endpoints from OpenAPI spec."""
    
    # Generate schemas first if requested
    if generate_schemas_flag:
        try:
            generate_schemas(spec_path, service_name)
        except Exception as e:
            print(f"Warning: Schema generation failed: {e}")
            print("Continuing with endpoint generation...")
    
    # Load OpenAPI spec
    spec_content = Path(spec_path).read_text()
    spec = yaml.safe_load(spec_content)
    
    # Setup Jinja2 environment
    template_dir = Path(__file__).parent / "templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_dir),
        trim_blocks=True,
        lstrip_blocks=True
    )
    
    # Add custom filters
    env.filters['snake_case'] = _snake_case
    
    # Load template
    template = env.get_template("endpoints.py.j2")
    
    # Generate routes
    routes = []
    imports = set()
    
    for path, path_item in spec.get("paths", {}).items():
        for verb, operation in path_item.items():
            if verb in ["get", "post", "put", "delete", "patch"]:
                request_model = _model_from_request(operation)
                response_model = _model_from_response(operation)
                path_params = _extract_path_params(path, operation)
                
                # Convert path parameters from camelCase to snake_case
                converted_path = path
                for param in path_params:
                    converted_path = converted_path.replace(
                        f"{{{param['original_name']}}}", 
                        f"{{{param['name']}}}"
                    )
                
                # Add imports for models
                if request_model:
                    imports.add(request_model)
                if response_model:
                    imports.add(response_model)
                
                route_code = template.render(
                    http_method=verb,
                    path=converted_path,
                    operation_id=operation["operationId"],
                    summary=operation.get("summary", ""),
                    request_model=request_model,
                    response_model=response_model,
                    path_params=path_params,
                    service_name=service_name,
                    status_code=201 if verb == "post" else (204 if verb == "delete" else 200)
                )
                routes.append(route_code.strip() + "\n")
    
    # Generate final file content
    service_class_name = f"{service_name.title()}Service"
    
    # Determine if we need List import
    typing_imports = ["Dict"]
    if any("List[" in model for model in imports if model):
        typing_imports.append("List")
    
    # Clean up imports - remove List[...] patterns and extract base models
    clean_imports = set()
    for imp in imports:
        if imp and "List[" in imp:
            # Extract the base model from List[Model]
            base_model = imp.replace("List[", "").replace("]", "")
            clean_imports.add(base_model)
        elif imp:
            clean_imports.add(imp)
    
    file_content = f"""# ⚠️ AUTO-GENERATED — DO NOT EDIT
# Generated from: {spec_path}
# Service: {service_name}

from typing import {', '.join(sorted(typing_imports))}
from fastapi import APIRouter, Depends, HTTPException

# Import schemas - these should already exist
from src.schemas.{service_name} import {', '.join(sorted(clean_imports)) if clean_imports else '# Add your schema imports here'}
# Import service layer - this should be created manually in src/services/
from src.services.{service_name}_service import {service_class_name}, get_{service_name}_service

router = APIRouter()


{chr(10).join(routes)}


@router.get("/health")
def health_check() -> Dict[str, str]:
    \"\"\"Health check endpoint.\"\"\"
    return {{"status": "healthy", "service": "{service_name}-service"}}
"""
    
    # Write to output file
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(file_content)
    
    print(f"Generated endpoints written to: {output_path}")
    print(f"Generated {len(routes)} endpoints")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate FastAPI endpoints and schemas from OpenAPI spec")
    parser.add_argument("spec_path", help="Path to OpenAPI YAML file")
    parser.add_argument("output_path", help="Output path for generated endpoints")
    parser.add_argument("--service-name", default="service", help="Service name for imports")
    parser.add_argument("--no-schemas", action="store_true", help="Skip schema generation")
    
    args = parser.parse_args()
    
    generate_endpoints(args.spec_path, args.output_path, args.service_name, not args.no_schemas)


if __name__ == "__main__":
    main() 