import os
import secrets
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from flask_socketio import SocketIO, join_room, leave_room, send, emit
import googleapiclient.discovery

app = Flask(__name__, static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:Original50!@localhost/Proiect'
app.config['SECRET_KEY'] = 'scrt123fasd'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'p.casi2003@gmail.com'
app.config['MAIL_PASSWORD'] = 'ohqp yqpz yvcb syqn'
app.config['GOOGLE_CLIENT_SECRET_FILE'] = r'D:\proiecte_py\A-Point\static\client_secret_523482229240-ohach88c36onpo88oflk43j2a355h7f4.apps.googleusercontent.com.json'
app.config['GOOGLE_CALENDAR_ID'] = 'f7b4aca72e5505a171b3280cc677610069f577f76b6983122c42672aebee306b@group.calendar.google.com'
app.config['GOOGLE_CALENDAR_TIMEZONE'] = 'Europe/Bucharest'

socketio = SocketIO(app)
user_rooms = {}


db = SQLAlchemy(app)
mail = Mail(app)


class User(db.Model):
    __tablename__='utilizatori'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    active = db.Column(db.Boolean, default=False)
    confirmation_code = db.Column(db.String(20))
    nume = db.Column(db.String(40), nullable=False)
    prenume = db.Column(db.String(40), nullable=False)


# Function to create Google Calendar service
def create_calendar_service():
    creds = None
    token_file = 'token.json'  # Path to store token.json file

    # Load previously stored token if available
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file)

    # If no valid credentials available, prompt the user to log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                app.config['GOOGLE_CLIENT_SECRET_FILE'],
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            creds = flow.run_local_server(port=50376)

        # Save the credentials for the next run
        with open(token_file, 'w') as token:
            token.write(creds.to_json())

    # Create Google Calendar service
    service = googleapiclient.discovery.build('calendar', 'v3', credentials=creds)
    return service

# Function to create Google Calendar event
def create_calendar_event(summary, start_datetime, end_datetime, description, attendees):
    service = create_calendar_service()
    event = {
        'summary': summary,
        'description': description,
        'start': {
            'dateTime': start_datetime,
            'timeZone': app.config['GOOGLE_CALENDAR_TIMEZONE'],
        },
        'end': {
            'dateTime': end_datetime,
            'timeZone': app.config['GOOGLE_CALENDAR_TIMEZONE'],
        },
        'attendees': attendees,
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 10},
            ],
        },
    }
    event_result = service.events().insert(calendarId=app.config['GOOGLE_CALENDAR_ID'], body=event).execute()
    print("Event creation response:", event_result)  # Log this to see the complete output
    return event_result['id']


# Send confirmation email
def send_confirmation_email(user):
    token = generate_confirmation_token(user.email)

    confirm_url = url_for('confirm_email', token=token, _external=True)
    msg = Message('Confirm your email', sender='p_casi2003@yahoo.ro', recipients=[user.email])
    msg.body = f'Please click the following link to activate your account: {confirm_url}'

    # Update the user's confirmation_code with the token
    user.confirmation_code = token

    # Commit the changes to the database
    db.session.commit()

    # Send the email
    mail.send(msg)

def generate_confirmation_token(email):
    token = secrets.token_urlsafe(20)
    # You can include the email in the token to make it unique
    return token

@app.route('/')
def Main_page():
    return render_template('Home.html')

@app.route('/chatroom/<room_number>')
def chatroom(room_number):
    return render_template('chatroom.html', room_number=room_number)

@socketio.on('join_room')
def handle_join_room(data):
    room_number = data['room_number']
    join_room(room_number)
    # Check if the user joining is a doctor
    user = get_current_user_role()
    if user == 'Medic':
        emit('doctor_joined', room=room_number)
    print(f'user has joined room {room_number}')
    emit('status', {'msg': f'user has joined the room.'}, room=room_number)

@socketio.on('send_message')
def handle_send_message(data):
    message = data['message']
    room_number = data['room_number']
    emit('receive_message', {'message': message}, room=room_number)
    print(f'Message sent to room {room_number}: {message}')


def get_current_user_role():
    user_email = request.cookies.get('user_email')
    user = User.query.filter_by(email=user_email,role='Medic').first()
    if user == None:
        return 'Pacient'
    else:
        return 'Medic'


@app.route('/Home.html')
def Home():
    return render_template('Home.html')

@app.route('/Chat.html', methods=['GET', 'POST'])
def chat_selection():
    medics = User.query.filter_by(role='Medic').all()
    if request.method == 'POST':
        # Get form data
        medic_email = request.form['medic']
        room_number = request.form['room_number']

        # Send email to medic with chat room link
        send_chat_link_email(medic_email, room_number)

        # Redirect to chat room with room number
        return redirect(url_for('chatroom', room_number=room_number))

    return render_template('Chat.html', medics=medics)
def send_chat_link_email(medic_email, room_number):
    # Construct the chat room URL
    chat_room_url = url_for('chatroom', room_number=room_number, _external=True)

    user_email = request.cookies.get('user_email')

    msg = Message('Chat Room', sender='p.casi2003@gmail.com', recipients=[medic_email])
    msg.body = f'You have a Chat request with {user_email}. Join the chat using this link: {chat_room_url}'
    mail.send(msg)

@app.route('/Programari.html', methods=['GET', 'POST'])
def Programari():
    medics = User.query.filter_by(role='Medic').all()

    if request.method == 'POST':
        medic_email = request.form['medic']
        print(medic_email)
        date = request.form['date']
        start_time = request.form['time']
        user_email = request.cookies.get('user_email')  # Extract user email from cookies

        # Calculate the end time by adding one hour to the start time
        start_datetime_str = f'{date}T{start_time}:00'
        start_datetime_obj = datetime.strptime(start_datetime_str, '%Y/%m/%dT%H:%M:%S')
        end_datetime_obj = start_datetime_obj + timedelta(hours=1)

        # Convert datetime objects back to string format
        start_datetime = start_datetime_obj.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_datetime = end_datetime_obj.strftime('%Y-%m-%dT%H:%M:%SZ')

        # Define attendees
        attendees = [{'email': user_email}, {'email': medic_email}]

        # Create events in Google Calendar for both medic and patient
        event_id = create_calendar_event(f'Appointment with {medic_email}', start_datetime, end_datetime, 'Appointment with patient', attendees)

        user_msg = Message('Appointment Confirmation', sender='p.casi2003@gmail.com', recipients=[user_email])
        user_msg.body = f'Your appointment with {medic_email} on {date} at {start_time} has been confirmed. Please check your calendar for details.'
        mail.send(user_msg)

        # Send email to selected medic
        medic_msg = Message('New Appointment', sender='p.casi2003@gmail.com', recipients=[medic_email])
        medic_msg.body = f'You have a new appointment scheduled on {date} at {start_time} with {user_email}. Please check your calendar for details.'
        mail.send(medic_msg)

        # Redirect to a success page to prevent duplicate submissions
        flash('Appointment successfully scheduled.')
        return redirect(url_for('Home'))

    return render_template('Programari.html', medics=medics)

@app.route('/Calendar.html')
def calendar():
    return render_template('Calendar.html')

@app.route('/Login_pacient.html')
def login_page():
    return render_template('Login_pacient.html')

@app.route('/Login_pacient.html', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['Email']
        password = request.form['Parola']
        user = User.query.filter_by(email=email).first()
        if user and user.password == password:
            if user.active:
                resp = make_response(redirect(url_for('Home')))
                resp.set_cookie('user_email', email, max_age=86400)  # Expires in one day
                return resp
        else:
            flash("Credentials are incorrect or account is not activated")
    return render_template('Login_pacient.html')

@app.route('/Sign-In.html', methods=['GET', 'POST'])
def Sign_In():
    if request.method == 'POST':
        nume=request.form['Nume']
        prenume=request.form['Prenume']
        email = request.form['Email']
        password = request.form['Parola']
        role = request.form['Rol']
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already exists. Please log in.')
            return redirect(url_for('login_page'))
        # Create a new user
        user = User(email=email, password=password, role=role, nume=nume, prenume=prenume)
        db.session.add(user)
        db.session.commit()
        # Send confirmation email
        send_confirmation_email(user)
        flash('Account created successfully. Please check your email to activate your account.')
        return redirect(url_for('login_page'))
    return render_template('Sign-In.html')

@app.route('/confirm.html/<token>')
def confirm_email(token):
    # Find the user associated with the token
    user = User.query.filter_by(confirmation_code=token).first()

    if user:
        # Mark the user as active
        user.active = True

        # Remove the confirmation code since it's no longer needed
        user.confirmation_code = None

        # Commit the changes to the database
        db.session.commit()

        # Flash a success message
        flash('Email confirmed successfully. Your account is now activated.')

        # Redirect the user to the login page
        return redirect(url_for('login_page'))
    else:
        # If the token is invalid or expired, show an error message
        flash('Invalid or expired confirmation token. Please try again or contact support.')
        return redirect(url_for('Home'))

if __name__ == '__main__':
    socketio.run(app, debug=True,allow_unsafe_werkzeug=True)
    app.run(debug=True)
