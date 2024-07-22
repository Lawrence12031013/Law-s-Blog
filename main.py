import os
from datetime import date
from functools import wraps
from smtplib import SMTP
from flask import Flask, abort, render_template, redirect, url_for, flash, request, send_from_directory
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor, upload_success, upload_fail
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from werkzeug.security import generate_password_hash, check_password_hash
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from dotenv import load_dotenv


# Load environment variables from .env
load_dotenv()

my_email = os.getenv('MY_EMAIL')
email_password = os.getenv('EMAIL_PASSWORD')
to_email = os.getenv('TO_EMAIL')

# Import your forms from the forms.py
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm, SendEmailForm

'''
Make sure the required packages are installed: 
Open the Terminal in PyCharm (bottom left). 
On Windows type:
python -m pip install -r requirements.txt

On MacOS type:
pip3 install -r requirements.txt

This will install the packages from the requirements.txt for this project.
'''

basedir = os.path.abspath(os.path.dirname(__file__))


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_KEY', 'default-secret-key')
Bootstrap5(app)

# TODO: Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)


app.config['CKEDITOR_FILE_UPLOADER'] = 'upload'
app.config['CKEDITOR_SERVE_LOCAL'] = True
# app.config['CKEDITOR_ENABLE_CSRF'] = True
app.config['UPLOAD_PATH'] = os.path.join(basedir, 'upload')

ckeditor = CKEditor(app)
# csrf = CSRFProtect(app)


@app.route('/file/<path:filename>')
def upload_files(filename):
    path = app.config['UPLOAD_PATH']
    return send_from_directory(path, filename)


@app.route('/upload', methods=['POST'])
def upload():
    f = request.files.get('upload')
    extension = f.filename.split('.')[-1].lower()
    if extension not in ['jpg', 'png', 'gif', 'jpeg']:
        return upload_fail(message='Only photos!')
    f.save(os.path.join(app.config['UPLOAD_PATH'], f.filename))
    url = url_for('upload_files', filename=f.filename)
    return upload_success(url=url, filename=f.filename)

# CREATE DATABASE
class Base(DeclarativeBase):
    pass
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///posts.db', )
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES
class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    author = relationship("User", back_populates="posts")
    comments = relationship('Comment', back_populates='parent_post')


# TODO: Create a User table for all your registered users. 
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    posts = relationship("BlogPost", back_populates="author")
    comments = relationship('Comment', back_populates='comment_author')


class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    comment_author = relationship('User', back_populates='comments')
    post_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("blog_posts.id"))
    parent_post = relationship('BlogPost', back_populates='comments')


def admin_only(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if current_user.id == 1:
            return f(*args, **kwargs)
        else:
            return abort(404)
    return wrap

with app.app_context():
    db.create_all()

# comment headshot
gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)

@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)

# TODO: Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()

    if form.validate_on_submit():
        register_password = form.passowrd.data
        email = form.email.data
        name = form.name.data
        if db.session.execute(db.select(User).where(User.email == email)).scalar():
            flash('You have already sign up with this email, log in instead.')
            return redirect(url_for('login'))
        elif db.session.execute(db.select(User).where(User.name == name)).scalar():
            flash('The name has been used.')
        else:
            salty_password = generate_password_hash(
                password=register_password,
                method='pbkdf2:sha256',
                salt_length=8
            )

            new_user = User(
                email=form.email.data,
                password=salty_password,
                name=form.name.data
            )

            db.session.add((new_user))
            db.session.commit()
            login_user(new_user)
            return redirect(url_for("get_all_posts"))
    return render_template("register.html", form=form)


# TODO: Retrieve a user from the database based on their email. 
@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()

    if form.validate_on_submit():
        login_email = form.email.data
        login_password = form.password.data
        result = db.session.execute(db.select(User).where(User.email == login_email))
        user = result.scalar()

        if not user:
            flash('The email or password you entered is incorrect!')
            return redirect(url_for('login'))
        elif not check_password_hash(user.password, login_password):
            flash('The email or password you entered is incorrect!')
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect(url_for('get_all_posts'))

    return render_template("login.html", form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()

    return render_template("index.html", all_posts=posts)


# TODO: Allow logged-in users to comment on posts
@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    form = CommentForm()
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash('You need to login or register to comment.')
            return redirect(url_for('login'))

        new_comment = Comment(
            text=form.text.data,
            comment_author=current_user,
            parent_post=requested_post
        )

        db.session.add(new_comment)
        db.session.commit()
        return redirect(url_for('show_post', post_id=requested_post.id))
    comments = db.session.execute(db.select(Comment).where(Comment.post_id == post_id)).scalars().all()
    return render_template("post.html", post=requested_post, form=form, current_user=current_user, comments=comments)


# TODO: Use a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)


# TODO: Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


# TODO: Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    comments_to_delete = Comment.query.filter_by(post_id=post_id).all()
    for comment in comments_to_delete:
        db.session.delete(comment)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=['GET', 'POST'])
def contact():
    form = SendEmailForm()
    if form.validate_on_submit():
        try:
            Subject = f'郵件通知 {form.name.data}'
            Subject = Header(Subject, 'utf-8').encode()
            email = MIMEMultipart('mixed')
            email['Subject'] = Subject
            Html = """\
                       <html>
                          <head></head>
                          <body>
                              <h3>From: """ + form['name'].data + """</h3>
                              <h3>Email: """ + form['email'].data + """</h3>
                              <h3>Message: """ + form['message'].data + """</h3>
                          </body>
                       </html>
                    """
            message = MIMEText(Html, 'html', 'utf-8')
            email.attach(message)

            server = SMTP('smtp.gmail.com', 587)
            server_res = server.ehlo()
            print(f'res 1==> {server_res}')
            smtp_ttls = server.starttls()
            print(f'start tls ==> {smtp_ttls}')
            smtp_login = server.login(user=my_email, password=email_password)
            print(f'SMTP login ==> {smtp_login}')

            server.sendmail(from_addr=my_email, to_addrs=to_email, msg=email.as_string())
            server.quit()
            flash(message='Email sent successfully!')
            print('Email sent successfully')
            return redirect(url_for("contact"))

        except Exception as e:
            print(f'Error sending email: {str(e)}')
            flash(message='Email sent failed!')
            return render_template("contact", error_message=str(e))  # Render an error page if something goes wrong

    return render_template("contact.html", form=form)


if __name__ == "__main__":
    app.run(debug=True)
