from flask import Flask, flash, redirect, url_for, render_template, request, send_from_directory, abort
import uuid
from werkzeug.utils import secure_filename
import os
import datetime
import click
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash


def create_app(test_config=None):

    app = Flask(__name__, instance_relative_config=True)

    app.config.from_pyfile('config.py', silent=True)
    app.config.from_mapping(SECRET_KEY='dev')

    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}
    MAX_FILE_SIZE_BYTES = 16 * 1024 * 1024

    os.makedirs(UPLOAD_FOLDER, exist_ok=True )

    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE_BYTES

    def allowed_file(filename):
        """ Check if the extension is acceptable."""
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///event_database2.db"

    class Base(DeclarativeBase):
        pass

    db = SQLAlchemy(model_class=Base)
    db.init_app(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'


    class Post(db.Model):
        id = mapped_column(db.Integer, primary_key=True)
        title = mapped_column(db.String)
        description = mapped_column(db.String)
        date = mapped_column(db.String)
        status = mapped_column(db.String)
        upload = mapped_column(db.String)
        published = mapped_column(db.Boolean, default=False)
        user_id = mapped_column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    class User(db.Model, UserMixin):
        id = mapped_column(db.Integer, primary_key=True)
        Firstname = mapped_column(db.String)
        Lastname = mapped_column(db.String)
        Username = mapped_column(db.String, unique=True, nullable=False)
        Email = mapped_column(db.String)
        Password = mapped_column(db.String, nullable=False)
        date = mapped_column(db.String)

    class Comment(db.Model):
        id = mapped_column(db.Integer, primary_key=True)
        content = mapped_column(db.String, nullable=False)
        post_id = mapped_column(db.Integer, db.ForeignKey('post.id'), nullable=False)
        user_id = mapped_column( db.Integer, db.ForeignKey('user.id'), nullable=False)
        date = mapped_column(db.String)
   
    class Like(db.Model):
        id = mapped_column(db.Integer, primary_key=True)
        post_id = mapped_column(db.Integer, db.ForeignKey('post.id'), nullable=False)
        user_id = mapped_column( db.Integer, db.ForeignKey('user.id'), nullable=False)
        __table_args__ = ( db.UniqueConstraint( 'post_id', 'user_id', name='unique_user_like_per_post'),)
        # like = mapped_column(db.String, nullable=False)


    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @click.command('init-db')
    def init_db_command():
        """Command for initializing the database"""
        with app.app_context():
            db.create_all()
            click.echo('Database created successfully')

    app.cli.add_command(init_db_command)


    @app.route('/post/<int:id>/comment', methods=['POST'])
    @login_required
    def add_comment(id):
        post = db.session.get(Post, id)

        if post is None or not post.published or post.status != "Active":
            abort(404)

        content = request.form.get('content', '').strip()

        if not content:
            flash('Please enter a comment.')
            return redirect(url_for('published_posts'))

        if len(content) > 2000:
            flash('Comments cannot exceed 2000 characters.')
            return redirect(url_for('published_posts'))

        comment = Comment(
            content=content,
            post_id=post.id,
            user_id=current_user.id,
            date=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )

        db.session.add(comment)
        db.session.commit()

        flash('Comment added successfully.')
        return redirect(url_for('published_posts'))


    @app.route('/post/<int:id>/like', methods=['POST'])
    @login_required
    def toggle_like(id):
        print("\n========== LIKE DEBUG START ==========")
        print("Route reached!")
        print("Post ID:", id)
        print("Logged-in user ID:", current_user.id)

        post = db.session.get(Post, id)

        if post is None:
            print("ERROR: Post not found.")
            abort(404)

        if not post.published or post.status != "Active":
            print("ERROR: Post is not published and active.")
            abort(404)

        existing_like = Like.query.filter_by(
            post_id=post.id,
            user_id=current_user.id
        ).first()

        try:
            if existing_like:
                print("Action: Removing existing like.")
                db.session.delete(existing_like)
            else:
                print("Action: Adding new like.")
                new_like = Like(
                    post_id=post.id,
                    user_id=current_user.id
                )
                db.session.add(new_like)

            db.session.commit()
            print("Database commit completed.")

            total_likes = Like.query.filter_by(
                post_id=post.id
            ).count()

            print("Total likes after commit:", total_likes)
            print("========== LIKE DEBUG END ==========\n")

        except Exception as error:
            db.session.rollback()
            print("LIKE ERROR:", repr(error))
            raise

        return redirect(url_for('published_posts'))

    @app.route('/post/<int:id>')
    @login_required
    def post(id):
        # return f"<h1>Post {id}</h1>" 
        post = Post.query.get(id)

        return render_template('post.html', post=post)

    @app.route('/delete/<int:id>')
    @login_required
    def delete(id):
        post = Post.query.filter_by(id=id)
        post = db.session.execute(post).scalar_one_or_none()

        post.status = "Deleted"

        # db.session.delete(post)
        db.session.commit()

        return redirect(url_for('home'))

    @app.route('/edit/<int:id>', methods=['GET', 'POST'])
    @login_required
    def edit(id):
        
        # return f"<h1>Post {id}</h1>" 
        if request.method == 'POST':
            print('here')
            post = Post.query.filter_by(id=id)
            post = db.session.execute(post).scalar_one_or_none()
            print(post)

            post.title = request.form['title']
            
            post.description = request.form['description']

            file = request.files.get('post_image')

            if file and file.filename != '' and allowed_file(file.filename):

                filename = secure_filename(file.filename)

                file.save(os.path.join(app.config['UPLOAD_FOLDER'],filename))

                post.upload = filename


            db.session.commit()

        edit = Post.query.get(id)

        return render_template('edit.html', edit=edit)


    @app.route('/upload', methods=['GET', 'POST'])
    def upload():
        if request.method == 'POST':

            if 'post_image' not in request.files:
                flash('No file path in the request')
                return 'expected file field not submitted'

            file = request.files['post_image']
            files = request.files['cover_image']
            if file.filename == '':
                return 'No file uploaded'

            # return file.filename
            # return str(allowed_file(file.filename))
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filesname = secure_filename(files.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                files.save(os.path.join(app.config['UPLOAD_FOLDER'], filesname))

                flash('File succesfully uploaded')
                return redirect(url_for('upload'))

        return render_template('upload.html')

    @app.route('/publish/<int:id>')
    @login_required
    def publish(id):
        post = db.session.get(Post, id)
        if post is None or post.user_id != current_user.id:
            abort(404)
        post.published = True
        db.session.commit()
        return redirect(url_for('home'))


    @app.route('/published')
    @login_required
    def published_posts():
        rows = db.session.execute(
            db.select(Post, User)
            .join(User, Post.user_id == User.id)
            .where(
                Post.published == True,
                Post.status == "Active"
            )
            .order_by(Post.date.desc())
        ).all()

        comments = Comment.query.all()

        users = User.query.all()
        comment_usernames = {
            user.id: user.Username for user in users
        }

        post_ids = [post.id for post, author in rows]

        # Initialize every displayed post with zero likes.
        like_counts = {post_id: 0 for post_id in post_ids}

        if post_ids:
            like_rows = db.session.execute(
                db.select(
                    Like.post_id,
                    db.func.count(Like.id)
                )
                .where(Like.post_id.in_(post_ids))
                .group_by(Like.post_id)
            ).all()

            for post_id, count in like_rows:
                like_counts[post_id] = count

            liked_post_ids = set(
                db.session.execute(
                    db.select(Like.post_id).where(
                        Like.user_id == current_user.id,
                        Like.post_id.in_(post_ids)
                    )
                ).scalars().all()
            )
        else:
            liked_post_ids = set()

        return render_template(
            'publish.html',
            rows=rows,
            comments=comments,
            comment_usernames=comment_usernames,
            like_counts=like_counts,
            liked_post_ids=liked_post_ids
        )


    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    @app.route('/', methods=['GET', 'POST'])
    @login_required
    def home():
        file = request.files.get('post_image')

        if file and file.filename != '' and allowed_file(file.filename):

            filename = secure_filename(file.filename)

            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        if request.method == 'POST':
            db.session.add(Post(title = request.form['postBox'], description=request.form['postDesc'], date=datetime.datetime.now().__str__(), status = "Active", upload=filename, user_id=current_user.id))
            db.session.commit()
            return redirect(url_for('home'))

        user_posts = db.session.execute(
            db.select(Post).where(Post.status == "Active", Post.user_id == current_user.id).order_by(Post.date)
        ).scalars().all()


        total_comments = db.session.execute(
            db.select(db.func.count(Comment.id))
            .join(Post, Comment.post_id == Post.id)
            .where(Post.user_id == current_user.id)
        ).scalar()

        return render_template('index.html', eventsList=user_posts, user=current_user, total_comments=total_comments)

            
    @app.route('/signup', methods=['GET', 'POST'])
    def signup():
        if request.method == 'POST':
            new_user = User(
                Firstname=request.form.get('firstName'),
                Lastname=request.form.get('lastName'),
                Username=request.form.get('userName'),
                Email=request.form.get('email'),
                Password=generate_password_hash(request.form.get('password')),
                date=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            db.session.add(new_user)
            db.session.commit()

            return redirect(url_for('login', welcome='✓ Congratulations, you have successfully created an account!'))

        # Pass all users as eventsList so the table renders them
        all_users = User.query.all()
        return render_template('signup.html', eventsList=all_users)


    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = None
        welcome = request.args.get('welcome')

        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')

            user = User.query.filter_by(Username=username).first()

            if user and check_password_hash(user.Password, password):
                login_user(user)
                return redirect(url_for('home'))
            else:
                error = 'Invalid username or password'

        return render_template('login.html', error=error, welcome=welcome)

    @app.route('/dashboard')
    @login_required
    def dashboard():
        return render_template('index.html', user=current_user)

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))


    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)