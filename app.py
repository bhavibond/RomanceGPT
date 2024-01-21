# Import necessary modules
import os
import random
import nltk
import logging
import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_paginate import Pagination, get_page_parameter
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, Email
from flask_mail import Mail, Message as FlaskMessage
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO
import base64

# Download NLTK data (if not already downloaded)
nltk.download('punkt')

app = Flask(__name__)

# App Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_default_secret_key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URI', 'sqlite:///messages.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['RESULTS_PER_PAGE'] = 5  # Number of messages per page
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = os.environ.get('MAIL_PORT', 587)
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', True)
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@romancegpt.com')
app.config['QUOTE_API_URL'] = 'https://quotes.rest/qod?category=love'
app.config['UPLOAD_FOLDER'] = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Configure Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Configure Flask-WTF
app.config['WTF_CSRF_ENABLED'] = True

# Configure Flask-Mail
mail = Mail(app)

# Set up logging
logging.basicConfig(filename='app.log', level=logging.INFO)

# Define User model for the database
db = SQLAlchemy(app)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    messages = db.relationship('Message', backref='user', lazy=True)
    is_admin = db.Column(db.Boolean, default=False)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    girlfriend_name = db.Column(db.String(100), nullable=False)
    romantic_message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

# Create database tables (run this once to initialize the database)
db.create_all()

# Function to generate a more varied romantic message using real-time data from the "They Said So" Quotes API
def generate_romantic_message(girlfriend_name, special_moments):
    if not girlfriend_name:
        girlfriend_name = "My Love"  # Use a default if girlfriend_name is not provided

    try:
        # Fetch real-time love quote from the "They Said So" Quotes API
        response = requests.get(app.config['QUOTE_API_URL'])
        quote_data = response.json()
        quote = quote_data['contents']['quotes'][0]['quote']
    except Exception as e:
        logging.error(f"Error fetching quote from API: {str(e)}")
        quote = "You make every moment special."

    # Construct the romantic message
    romantic_message = f"{girlfriend_name}, {quote}. Our love grows stronger every day."

    # Save the message in the database
    new_message = Message(user=current_user, girlfriend_name=girlfriend_name, romantic_message=romantic_message)
    db.session.add(new_message)
    db.session.commit()

    # Notify user via email (optional)
    send_notification_email(new_message)

    # Return the generated message and timestamp
    return {
        "girlfriend_name": girlfriend_name,
        "romantic_message": romantic_message,
        "timestamp": new_message.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
    }

# Flask-WTF Form for user registration
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=50)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Register')

# Send notification email to the user
def send_notification_email(message):
    try:
        msg = FlaskMessage("New Romantic Message",
                           recipients=[current_user.email],
                           body=f"Dear {current_user.username},\n\n"
                                f"Your romantic message for {message.girlfriend_name} has been created. "
                                f"Here is the message:\n\n'{message.romantic_message}'\n\n"
                                f"Cheers,\nThe Romantic Message App")
        mail.send(msg)
    except Exception as e:
        logging.error(f"Error sending email notification: {str(e)}")

# Routes
@app.route("/")
@login_required
def index():
    return render_template("index.html", user=current_user)

@app.route("/generate_message", methods=["POST"])
@login_required
def ajax_generate_message():
    data = request.get_json()
    girlfriend_name = data.get("girlfriend_name", "")
    special_moments = data.get("special_moments", "")

    # Perform form validation
    if not girlfriend_name:
        flash("Please provide your girlfriend's name.", "danger")
        return jsonify({"error": "Missing girlfriend's name"})

    # Generate a romantic message
    generated_message = generate_romantic_message(girlfriend_name, special_moments)

    return jsonify(generated_message)

@app.route("/get_message_history", methods=["GET"])
@login_required
def ajax_get_message_history():
    page = request.args.get(get_page_parameter(), type=int, default=1)
    messages = current_user.messages.order_by(Message.timestamp.desc()).paginate(page, app.config['RESULTS_PER_PAGE'], False)
    formatted_history = [
        {
            "girlfriend_name": message.girlfriend_name,
            "romantic_message": message.romantic_message,
            "timestamp": message.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for message in messages.items
    ]
    pagination = Pagination(page=page, total=messages.total, per_page=app.config['RESULTS_PER_PAGE'], css_framework='bootstrap4')

    return render_template("message_history.html", message_history=formatted_history, pagination=pagination)

@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data, method='sha256')
        user = User(username=form.username.data, password=hashed_password, email=form.email.data)
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template("register.html", form=form)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password. Please try again.', 'danger')
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# Placeholder for additional routes
# @app.route("/example_route")
# def example_route():
   # return "This is an example route."

@app.route("/settings")
@login_required
def user_settings():
    # Retrieve and display user-specific settings
    user_settings = get_user_settings(current_user)
    return render_template("user_settings.html", user_settings=user_settings)

@app.route("/submit_feedback", methods=["POST"])
def submit_feedback():
    if request.method == "POST":
        feedback = request.form.get("feedback")
        # Process and store the feedback in the database
        store_feedback(feedback)
        flash("Thank you for your feedback!", "success")
    return redirect(url_for("index"))

@app.route("/admin_dashboard")
@login_required
def admin_dashboard():
    # Check if the current user has admin privileges
    if current_user.is_admin:
        # Render the admin dashboard
        return render_template("admin_dashboard.html")
    else:
        flash("Access denied. Admin privileges required.", "danger")
        return redirect(url_for("index"))

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500

# File uploads
@app.route("/upload_image", methods=["POST"])
@login_required
def upload_image():
    if request.method == "POST":
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            flash('File uploaded successfully', 'success')
            return redirect(url_for('index'))

# Displaying uploaded images
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Data visualization
@app.route("/visualization")
def data_visualization():
    # Generate sample data and create a simple plot
    x = np.linspace(0, 10, 100)
    y = np.sin(x)
    plt.plot(x, y)
    plt.xlabel("X-axis")
    plt.ylabel("Y-axis")
    plt.title("Sample Data Visualization")
    
    # Save the plot to a BytesIO object
    img_bytes = BytesIO()
    plt.savefig(img_bytes, format='png')
    img_bytes.seek(0)
    
    # Encode the image to base64 for embedding in HTML
    img_base64 = base64.b64encode(img_bytes.read()).decode('utf-8')
    
    return render_template("data_visualization.html", img_base64=img_base64)

# Change the user's password
@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        # Placeholder: Implement password change logic
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        if new_password == confirm_password:
            # Placeholder: Update the user's password in the database
            current_user.password = generate_password_hash(new_password, method='sha256')
            db.session.commit()
            flash("Password changed successfully", "success")
        else:
            flash("Password and confirmation do not match", "danger")
    return render_template("change_password.html")

# Displaying upcoming special occasions
@app.route("/special_occasions")
@login_required
def special_occasions():
    # Retrieve and display upcoming special occasions
    upcoming_occasions = get_upcoming_occasions()
    return render_template("special_occasions.html", upcoming_occasions=upcoming_occasions)

# Get upcoming special occasions
def get_upcoming_occasions():
    # Implement logic to fetch upcoming occasions from a database or external API
    upcoming_occasions = [
        {"name": "Anniversary", "date": "2024-05-15"},
        {"name": "Birthday", "date": "2024-07-22"},
        # Add more occasions as needed
    ]
    return upcoming_occasions

# Display recommended gifts
@app.route("/recommended_gifts")
@login_required
def recommended_gifts():
    # Retrieve and display recommended gifts based on user preferences
    user_preferences = get_user_preferences(current_user)
    recommended_gifts = get_recommendations(user_preferences)
    return render_template("recommended_gifts.html", recommended_gifts=recommended_gifts)

# Get user preferences
def get_user_preferences(user):
    # Implement logic to fetch user preferences from the database
    # For example, preferred gift categories, favorite colors, etc.
    return {"favorite_category": "Jewelry", "favorite_color": "Blue"}

# Get gift recommendations
def get_recommendations(user_preferences):
    # Implement logic to generate gift recommendations based on preferences
    # For example, recommend jewelry if it's their favorite category
    if user_preferences.get("favorite_category") == "Jewelry":
        return ["Necklace", "Bracelet", "Earrings"]
    else:
        return ["Customized Photo Frame", "Handwritten Love Letter", "Experience Day"]
            
# ... (Other potential enhancements soon)

if __name__ == "__main__":
    app.run(debug=True)
