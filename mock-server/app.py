from flask import Flask, jsonify, request
import json
import os
import logging
from functools import wraps

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global customers data
customers_data = []

def load_customers():
    """Load customers data from JSON file with error handling"""
    try:
        data_path = os.path.join(os.path.dirname(__file__), 'data', 'customers.json')
        
        if not os.path.exists(data_path):
            logger.error(f"Customer data file not found at: {data_path}")
            raise FileNotFoundError(f"Customer data file not found")
        
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            raise ValueError("Customer data must be a list")
        
        logger.info(f"Successfully loaded {len(data)} customers from JSON file")
        return data
    
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format in customers.json: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading customer data: {e}")
        raise

def error_handler(f):
    """Decorator for consistent error handling"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Validation error in {f.__name__}: {e}")
            return jsonify({
                "error": "Validation error",
                "message": str(e)
            }), 400
        except Exception as e:
            logger.error(f"Unexpected error in {f.__name__}: {e}", exc_info=True)
            return jsonify({
                "error": "Internal server error",
                "message": "An unexpected error occurred"
            }), 500
    return decorated_function

def validate_pagination(page, limit, max_limit=100):
    """Validate pagination parameters"""
    if page < 1:
        raise ValueError("Page must be greater than 0")
    if limit < 1:
        raise ValueError("Limit must be greater than 0")
    if limit > max_limit:
        raise ValueError(f"Limit cannot exceed {max_limit}")
    return True

# Initialize customers data on startup
try:
    customers_data = load_customers()
except Exception as e:
    logger.critical(f"Failed to initialize application: {e}")
    customers_data = []

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "mock-server",
        "customers_loaded": len(customers_data)
    }), 200

@app.route('/api/customers', methods=['GET'])
@error_handler
def get_customers():
    """Get paginated list of customers"""
    # Parse and validate pagination parameters
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
    except ValueError:
        return jsonify({
            "error": "Invalid parameters",
            "message": "Page and limit must be valid integers"
        }), 400
    
    # Validate pagination
    validate_pagination(page, limit)
    
    # Calculate pagination
    total = len(customers_data)
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    
    # Check if page is out of range
    if start_idx >= total and total > 0:
        return jsonify({
            "error": "Page out of range",
            "message": f"Requested page {page} exceeds available data"
        }), 400
    
    paginated_customers = customers_data[start_idx:end_idx]
    
    logger.info(f"Fetched page {page} with {len(paginated_customers)} customers")
    
    return jsonify({
        "data": paginated_customers,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if total > 0 else 0
    }), 200

@app.route('/api/customers/<customer_id>', methods=['GET'])
@error_handler
def get_customer(customer_id):
    """Get single customer by ID"""
    if not customer_id or not customer_id.strip():
        return jsonify({
            "error": "Invalid customer ID",
            "message": "Customer ID cannot be empty"
        }), 400
    
    customer = next(
        (c for c in customers_data if c.get('customer_id') == customer_id),
        None
    )
    
    if customer:
        logger.info(f"Retrieved customer: {customer_id}")
        return jsonify({"data": customer}), 200
    else:
        logger.warning(f"Customer not found: {customer_id}")
        return jsonify({
            "error": "Customer not found",
            "message": f"No customer found with ID: {customer_id}"
        }), 404

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        "error": "Not found",
        "message": "The requested resource was not found"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        "error": "Internal server error",
        "message": "An unexpected error occurred"
    }), 500

if __name__ == '__main__':
    logger.info("Starting Flask Mock Server on port 5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
