from flask import Flask, render_template, request, jsonify, flash
from functools import wraps
from datetime import datetime, timedelta
from werkzeug.middleware.proxy_fix import ProxyFix
import openai
from flask_caching import Cache
import os

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config.from_object(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})
app.secret_key = 'your_secret_key'  # Replace with a secure secret key

# Load sensitive information from environment variables
openai.api_key = os.environ.get('OPENAI_API_KEY')

# Rate Limiting
REQUESTS_PER_MINUTE = 5
MINUTE = 60

# Dictionary to store request timestamps for rate limiting
request_timestamps = {}


class ValidationError(Exception):
    def __init__(self, details):
        self.details = details


class OpenAIError(Exception):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response


class UnexpectedError(Exception):
    pass


def rate_limit(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        client_ip = request.remote_addr

        # Check if the client has exceeded the rate limit
        exceeded_rate_limit, remaining_time = has_exceeded_rate_limit(client_ip)

        if exceeded_rate_limit:
            flash('Rate limit exceeded. Please try again later.')
            return jsonify({"error": "Rate limit exceeded. Please try again later.", "remaining_time": remaining_time}), 429

        return func(*args, **kwargs)

    return wrapper


def has_exceeded_rate_limit(client_ip):
    current_time = datetime.now()

    if client_ip not in request_timestamps:
        request_timestamps[client_ip] = [current_time]
    else:
        timestamps = request_timestamps[client_ip]

        # Remove timestamps older than 1 minute
        request_timestamps[client_ip] = [t for t in timestamps if current_time - t < timedelta(minutes=1)]

        # Check if rate limit is exceeded
        if len(request_timestamps[client_ip]) >= REQUESTS_PER_MINUTE:
            remaining_time = (timestamps[-1] + timedelta(minutes=1) - current_time).seconds
            return True, remaining_time

        request_timestamps[client_ip].append(current_time)

    return False, 0


def validate_input(girlfriend_name, special_moments):
    errors = {}

    if not girlfriend_name:
        errors['girlfriendName'] = 'Please enter your girlfriend\'s name.'

    if not special_moments:
        errors['specialMoments'] = 'Please enter some special moments.'

    return errors


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        return generate_message()
    # Load the history of generated messages
    history = load_message_history()
    return render_template('index.html', history=history)


def load_message_history():
    # Load the message history from cache or create an empty list
    history = cache.get('message_history') or []
    return history


def save_to_message_history(message):
    # Save the generated message to the history
    history = load_message_history()
    history.append(message)
    # Keep the history limited to the last 10 messages for simplicity
    history = history[-10:]
    cache.set('message_history', history)


@app.route('/generate_message', methods=['POST'])
@rate_limit
def generate_message():
    try:
        # Retrieve input from the request
        girlfriend_name = request.form.get('girlfriend_name')
        special_moments = request.form.get('special_moments')

        # Validate input
        errors = validate_input(girlfriend_name, special_moments)

        if errors:
            raise ValidationError(errors)

        # Check if the message is already in the cache
        cache_key = f"{girlfriend_name}_{special_moments}"
        cached_message = cache.get(cache_key)

        if cached_message:
            flash('Romantic message retrieved from cache!')
            return jsonify({"romantic_message": cached_message, "from_cache": True})
        else:
            app.logger.debug(f"Cache miss: Key - {cache_key}")

        # Create a prompt for OpenAI API
        prompt = f"Compose a romantic message for {girlfriend_name}. Highlight some special moments, like {special_moments}."

        # Use the OpenAI API to generate a personalized romantic message
        with timing_context():
            response = openai.Completion.create(
                engine="text-davinci-002",
                prompt=prompt,
                max_tokens=150
            )

        # Check the OpenAI API response for errors
        if 'choices' not in response or not response['choices']:
            app.logger.error(f"Error in OpenAI API response: {response}")
            raise OpenAIError("Failed to generate a romantic message. Please try again.", response=response)

        # Extract the generated romantic message
        romantic_message = response['choices'][0]['text']

        # Store the generated message in the cache for future use
        cache.set(cache_key, romantic_message)

        # Save the generated message to the message history
        save_to_message_history({"girlfriend_name": girlfriend_name, "message": romantic_message, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

        # Log successful generation
        app.logger.info(f"Generated romantic message for {girlfriend_name}")

        flash('Romantic message generated successfully!')
        return jsonify({"romantic_message": romantic_message, "from_cache": False})
    except ValidationError as ve:
        flash('Validation error. Please check your input.')
        app.logger.error(f"Validation error: {str(ve.details)}")
        return jsonify({"error": "Validation error", "details": ve.details}), 400
    except OpenAIError as oae:
        flash('Failed to generate a romantic message. Please try again later.')
        app.logger.error(f"OpenAI API error: {str(oae)}")
        if oae.response:
            log_openai_error(oae.response)
            return jsonify({"error": "Failed to generate a romantic message. Please try again later."}), 500
        else:
            return jsonify({"error": "Failed to generate a romantic message. Please try again later."}), 500
    except Exception as e:
        flash('An unexpected error occurred. Please try again later.')
        app.logger.error(f"Unexpected error: {str(e)}")
        raise UnexpectedError("An unexpected error occurred. Please try again later.") from e


def timing_context():
    start_time = datetime.now()
    yield
    end_time = datetime.now()
    elapsed_time = end_time - start_time
    app.logger.debug(f"Time taken: {elapsed_time}")


def log_openai_error(response):
    if 'error' in response:
        app.logger.error(f"OpenAI API error: {response['error']['message']}")
        if 'code' in response['error']:
            app.logger.error(f"Error Code: {response['error']['code']}")
        if 'details' in response['error']:
            app.logger.error(f"Error Details: {response['error']['details']}")


@app.route('/get_message_history', methods=['GET'])
def get_message_history():
    history = load_message_history()
    return jsonify({"message_history": history})


if __name__ == "__main__":
    app.run(debug=True)
