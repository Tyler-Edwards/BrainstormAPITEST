"""API endpoints for test management."""
from typing import List, Optional, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.schemas.test import (
    TestRunCreate, TestRunResponse, TestRunList, 
    TestResultResponse, TestResultList, TestInfo,
    TestCategoriesResponse, TestsResponse, TestRegistryResponse,
    ModelSpecificTestsResponse
)
from app.services import test_service


router = APIRouter()


@router.get("/registry")
async def get_test_registry(
    modality: Optional[str] = Query(None, description="Filter tests by modality (e.g., 'NLP', 'Vision')"),
    model_type: Optional[str] = Query(None, description="Filter tests by model type/sub-type (e.g., 'Text Generation', 'Question Answering')"),
    category: Optional[str] = Query(None, description="Filter tests by category (e.g., 'bias', 'toxicity', 'robustness')"),
    include_config: bool = Query(False, description="Include default configuration for each test")
):
    """
    Get the test registry, optionally filtered by modality, model type, and category.
    
    - **modality**: Filter tests by modality (e.g., 'NLP', 'Vision')
    - **model_type**: Filter tests by model type/sub-type (e.g., 'Text Generation', 'Question Answering')
    - **category**: Filter tests by category (e.g., 'bias', 'toxicity', 'robustness')
    - **include_config**: Whether to include default configuration in the response
    
    The frontend should call this endpoint with both modality and model_type to get
    tests specifically applicable to a particular model.
    """
    try:
        tests = await test_service.get_available_tests(modality, model_type, category)
        
        # If include_config is False, remove the default_config and parameter_schema from the response
        if not include_config:
            for test_id in tests:
                tests[test_id].pop("default_config", None)
                tests[test_id].pop("parameter_schema", None)
        
        return {
            "tests": tests, 
            "count": len(tests),
            "filters": {
                "modality": modality,
                "model_type": model_type,
                "category": category
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving test registry: {str(e)}")


@router.get("/model-tests")
async def get_model_specific_tests(
    modality: str = Query(..., description="Model modality (e.g., 'NLP', 'Vision')"),
    model_type: str = Query(..., description="Model type (e.g., 'Text Generation', 'Question Answering')"),
    include_config: bool = Query(True, description="Include default configuration for each test"),
    category: Optional[str] = Query(None, description="Filter by test category (e.g., 'bias', 'toxicity', 'robustness')")
):
    """
    Get tests specifically applicable to a model based on its modality and type.
    
    This endpoint is optimized for frontend use to retrieve only the tests that
    are relevant for a specific model being tested.
    
    All parameters except category are required:
    - **modality**: Model modality (e.g., 'NLP', 'Vision')
    - **model_type**: Model type (e.g., 'Text Generation', 'Question Answering')
    - **include_config**: Whether to include default configuration in the response
    - **category**: Optional filter by test category
    """
    try:
        # Get tests that match all specified criteria
        tests = await test_service.get_available_tests(modality, model_type, category)
            
        # If include_config is False, remove the default_config from the response
        if not include_config:
            for test_id in tests:
                tests[test_id].pop("default_config", None)
                tests[test_id].pop("parameter_schema", None)
        
        return {
            "tests": tests,
            "count": len(tests),
            "model_info": {
                "modality": modality,
                "type": model_type,
                "category_filter": category
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving model-specific tests: {str(e)}")


@router.post("/run", status_code=201)
async def create_test_run(
    test_run_data: TestRunCreate
):
    """
    Create a new test run.
    
    Expects a request body with the following structure:
    ```json
    {
      "test_run_id": "uuid-from-websocket-connection",
      "test_ids": ["prompt_injection_test"],
      "model_settings": {
        "model_id": "gpt2",
        "modality": "NLP",
        "sub_type": "Text Generation", 
        "source": "huggingface",
        "api_key": "your-api-key"
      },
      "parameters": {
        "prompt_injection_test": {
          "max_samples": 100
        }
      }
    }
    ```
    
    - `test_run_id`: Required field containing the UUID received from WebSocket connection
    - `test_ids`: Required array of test IDs to run
    - `model_settings`: Required object with model configuration
      - `model_id`: Required field identifying the model
      - Other fields are optional but recommended
    - `parameters`: Optional object with test-specific parameters
    
    Important: You MUST connect to the WebSocket endpoint at `/ws/tests` first to obtain
    a test_run_id, then provide that ID when creating a test run.
    """
    try:
        # Check if test_run_id is provided
        if not test_run_data.test_run_id:
            raise ValueError("test_run_id is required. Connect to WebSocket endpoint at /ws/tests first to obtain an ID.")
            
        test_run = await test_service.create_test_run(test_run_data)
        
        # Format the response with the expected structure for the frontend
        return {
            "task_id": str(test_run["id"]),
            "status": test_run["status"],
            "message": "Test run created successfully",
            "test_run": test_run
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating test run: {str(e)}")


@router.get("/runs")
async def get_test_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100)
):
    """
    Get a list of test runs.
    """
    test_runs = await test_service.get_test_runs(skip, limit)
    return {"test_runs": test_runs, "count": len(test_runs)}


@router.get("/runs/{test_run_id}")
async def get_test_run(
    test_run_id: UUID
):
    """
    Get a test run by ID.
    """
    test_run = await test_service.get_test_run(test_run_id)
    if not test_run:
        raise HTTPException(status_code=404, detail=f"Test run with ID {test_run_id} not found")
    return test_run


@router.get("/runs/{test_run_id}/results")
async def get_test_results(
    test_run_id: UUID
):
    """
    Get test results for a test run.
    """
    # First check if the test run exists
    test_run = await test_service.get_test_run(test_run_id)
    if not test_run:
        raise HTTPException(status_code=404, detail=f"Test run with ID {test_run_id} not found")
    
    results = await test_service.get_test_results(test_run_id)
    return {"results": results, "count": len(results)}


@router.get("/results/{test_run_id}")
async def get_test_results_alias(
    test_run_id: UUID
):
    """
    Get test results for a test run (alias for frontend compatibility).
    """
    return await get_test_results(test_run_id)


@router.get("/categories")
async def get_test_categories():
    """
    Get all available test categories.
    
    This endpoint returns a list of all test categories available in the system,
    which can be used for filtering tests.
    """
    try:
        # Get all tests from the registry
        all_tests = await test_service.get_available_tests()
        
        # Extract unique categories
        categories = set()
        for test_id, test in all_tests.items():
            if "category" in test:
                categories.add(test["category"])
        
        # Convert to list and sort
        category_list = sorted(list(categories))
        
        return {
            "categories": category_list,
            "count": len(category_list)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving test categories: {str(e)}")


@router.get("/")
async def get_all_tests(
    include_config: bool = Query(False, description="Include default configuration for each test")
):
    """
    Get all available tests without any filtering.
    
    This is a convenience endpoint for the frontend to get all tests at once.
    """
    try:
        tests = await test_service.get_available_tests()
        
        # If include_config is False, remove the default_config and parameter_schema from the response
        if not include_config:
            for test_id in tests:
                tests[test_id].pop("default_config", None)
                tests[test_id].pop("parameter_schema", None)
        
        return {
            "tests": tests,
            "count": len(tests)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving tests: {str(e)}")


@router.get("/status/{test_run_id}")
async def get_test_status(
    test_run_id: UUID
):
    """
    Simple placeholder for test status that returns a minimal response.
    """
    # Return a minimal static response without doing any real work
    return {
        "task_id": str(test_run_id),
        "status": "completed",
        "progress": 100,
        "message": "Status check disabled",
        "results_count": 0,
        "initialization_complete": True
    }


@router.get("/debug/runs")
async def debug_get_all_test_runs():
    """
    Debug endpoint to get all test runs in memory.
    This helps diagnose issues with test execution.
    """
    from app.services.test_service import test_runs
    
    # Create a safe copy of test runs to avoid serialization issues
    safe_runs = {}
    for run_id, run in test_runs.items():
        try:
            safe_run = {
                "id": str(run.get("id", "")),
                "model_id": str(run.get("model_id", "")),
                "test_ids": run.get("test_ids", []),
                "status": run.get("status", "unknown"),
                "start_time": str(run.get("start_time", "")),
                "end_time": str(run.get("end_time", "")),
                "created_at": str(run.get("created_at", "")),
                "updated_at": str(run.get("updated_at", "")),
                "summary_results": run.get("summary_results", {})
            }
            safe_runs[str(run_id)] = safe_run
        except Exception as e:
            safe_runs[str(run_id)] = {"error": f"Failed to serialize: {str(e)}"}
    
    return {
        "count": len(safe_runs),
        "test_runs": safe_runs
    }


@router.get("/debug/websocket/{test_run_id}")
async def debug_websocket_connection(test_run_id: str):
    """
    Debug endpoint to test WebSocket connections.
    Sends a test notification to all clients connected to a test run.
    """
    from app.core.websocket import manager as websocket_manager
    from app.services.test_service import test_runs, serialize_datetime
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"Debug WebSocket notification for test run {test_run_id}")
    
    # Check if the test run exists
    test_run = test_runs.get(test_run_id)
    test_run_info = "Test run exists" if test_run else "Test run does not exist"
    
    # Send a test notification
    try:
        await websocket_manager.send_notification(
            test_run_id,
            serialize_datetime({
                "type": "debug_message",
                "test_run_id": test_run_id,
                "message": "This is a debug message from the API",
                "test_run_info": test_run_info
            })
        )
        return {
            "success": True,
            "message": "Debug notification sent",
            "test_run_exists": test_run is not None,
            "test_run_info": test_run_info
        }
    except Exception as e:
        logger.error(f"Error sending debug notification: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "test_run_exists": test_run is not None,
            "test_run_info": test_run_info
        }


@router.get("/debug/run-status/{test_run_id}")
async def debug_test_run_status(test_run_id: str):
    """
    Debug endpoint to check the status of a test run and its execution.
    """
    from app.services.test_service import test_runs, test_results
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"Checking status for test run {test_run_id}")
    
    # Get test run
    test_run = test_runs.get(test_run_id)
    if not test_run:
        return {
            "exists": False,
            "message": f"Test run {test_run_id} not found"
        }
    
    # Get results for this test run
    run_results = []
    for result_id, result in test_results.items():
        if result.get("test_run_id") == test_run_id:
            run_results.append({
                "id": result_id,
                "test_id": result.get("test_id"),
                "test_name": result.get("test_name"),
                "status": result.get("status"),
                "score": result.get("score"),
                "created_at": str(result.get("created_at", ""))
            })
    
    # Create a safe copy of the test run to avoid serialization issues
    safe_run = {
        "id": str(test_run.get("id", "")),
        "target_id": str(test_run.get("target_id", "")),
        "test_ids": test_run.get("test_ids", []),
        "status": test_run.get("status", "unknown"),
        "start_time": str(test_run.get("start_time", "")),
        "end_time": str(test_run.get("end_time", "")),
        "created_at": str(test_run.get("created_at", "")),
        "updated_at": str(test_run.get("updated_at", "")),
        "summary_results": test_run.get("summary_results", {})
    }
    
    return {
        "exists": True,
        "test_run": safe_run,
        "results_count": len(run_results),
        "results": run_results
    }


@router.get("/debug/available-tests")
async def debug_available_tests():
    """
    Debug endpoint to get all available test IDs and their details.
    This helps developers see what test IDs are available for testing.
    """
    from app.test_registry import test_registry
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Get all available tests
    tests = await test_service.get_available_tests()
    
    # Create a simplified list of test IDs with their details
    test_list = []
    for test_id, test_info in tests.items():
        test_list.append({
            "id": test_id,
            "name": test_info.get("name", ""),
            "category": test_info.get("category", ""),
            "description": test_info.get("description", ""),
            "compatible_modalities": test_info.get("compatible_modalities", []),
            "compatible_sub_types": test_info.get("compatible_sub_types", [])
        })
    
    return {
        "count": len(test_list),
        "tests": test_list
    } 