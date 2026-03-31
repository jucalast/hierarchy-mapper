from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

# This will track rate limits based on the user's IP.
# If integrating, you can change 'get_remote_address' to a function that 
# reads a token or tenant_id from the request headers to track limits per-client.
limiter = Limiter(key_func=get_remote_address)
