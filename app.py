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

    app.config['SQLALCHEMY_DATABASE_URI'] = ("sqlite:///" + os.path.join(app.root_path,"var","app-instance","event_database2.db"))

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

    class Follow(db.Model):
        __tablename__ = 'follow'
        id = mapped_column(db.Integer, primary_key=True)
        follower_id = mapped_column( db.Integer, db.ForeignKey('user.id'), nullable=False )
        following_id = mapped_column( db.Integer, db.ForeignKey('user.id'), nullable=False)
        date = mapped_column(db.String)
        __table_args__ = (
            db.UniqueConstraint( 'follower_id', 'following_id', name='unique_user_follow' ),
            db.CheckConstraint( 'follower_id != following_id', name='prevent_self_follow' )
        )

    class Comment(db.Model):
        id = mapped_column(db.Integer, primary_key=True)
        content = mapped_column(db.String, nullable=False)
        post_id = mapped_column(db.Integer, db.ForeignKey('post.id'), nullable=False)
        user_id = mapped_column( db.Integer, db.ForeignKey('user.id'), nullable=False)
        date = mapped_column(db.String)
   

    class Like(db.Model):
        __tablename__ = 'post_like'
        
        id = mapped_column(db.Integer, primary_key=True)
        post_id = mapped_column( db.Integer, db.ForeignKey('post.id'), nullable=False)
        user_id = mapped_column( db.Integer, db.ForeignKey('user.id'), nullable=False)
        __table_args__ = ( db.UniqueConstraint( 'post_id', 'user_id', name='unique_user_like_per_post'),)

    class Notification(db.Model):
        __tablename__ = 'notification'

        id = mapped_column(db.Integer, primary_key=True)
        recipient_id = mapped_column(db.Integer, db.ForeignKey('user.id'), nullable=False)
        actor_id = mapped_column(db.Integer, db.ForeignKey('user.id'), nullable=False)
        notification_type = mapped_column(db.String, nullable=False)
        post_id = mapped_column(db.Integer, db.ForeignKey('post.id'), nullable=True)
        is_read = mapped_column(db.Boolean, default=False, nullable=False)
        date = mapped_column(db.String, nullable=False)

    @app.context_processor
    def inject_unread_notification_count():
        unread_notification_count = 0

        if current_user.is_authenticated:
            unread_notification_count = Notification.query.filter_by(
                recipient_id=current_user.id,
                is_read=False).count()

        return { 'unread_notification_count': unread_notification_count 
        }

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


    @app.route('/people')
    @login_required
    def people():

        search = request.args.get('search', '').strip()

        users_query = User.query.filter(User.id != current_user.id)

        if search:
            users_query = users_query.filter(
                db.or_(
                    User.Firstname.ilike(f'%{search}%'),
                    User.Lastname.ilike(f'%{search}%'),
                    User.Username.ilike(f'%{search}%')
                )
            )

        all_users = users_query.order_by(User.Username).all()

        # Get the IDs of users the current user follows.
        following_ids = {
            follow.following_id
            for follow in Follow.query.filter_by(
                follower_id=current_user.id
            ).all()
        }

        return render_template(
            'people.html',
            all_users=all_users,
            search=search,
            following_ids=following_ids
        )


    
    @app.route('/profile/<username>')
    @login_required
    def profile(username):

        # Find the user whose profile is being viewed.
        person = User.query.filter_by(Username=username).first_or_404()

        # Count users who follow this person.
        followers_count = Follow.query.filter_by(
            following_id=person.id
        ).count()

        # Count users this person follows.
        following_count = Follow.query.filter_by(
            follower_id=person.id
        ).count()

        # Check whether the logged-in user follows this person.
        is_following = Follow.query.filter_by(
            follower_id=current_user.id,
            following_id=person.id
        ).first() is not None

        # Retrieve this user's active, published events.
        user_posts = Post.query.filter_by(
            user_id=person.id,
            published=True,
            status="Active"
        ).order_by(Post.date.desc()).all()

        # Get the IDs of the events displayed on this profile.
        post_ids = [post.id for post in user_posts]

        # Retrieve comments belonging to these events.
        if post_ids:
            comments = Comment.query.filter(
                Comment.post_id.in_(post_ids)
            ).all()
        else:
            comments = []

        # Get usernames for displaying comment authors.
        users = User.query.all()
        comment_usernames = {
            user.id: user.Username for user in users
        }

        # Start every event with a like count of zero.
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

            # Find which events the logged-in user has liked.
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

        # Pair each event with its author.
        rows = [(post, person) for post in user_posts]

        # Display the profile.
        return render_template(
            'profile.html',
            person=person,
            rows=rows,
            comments=comments,
            comment_usernames=comment_usernames,
            like_counts=like_counts,
            liked_post_ids=liked_post_ids,
            is_following=is_following,
            followers_count=followers_count,
            following_count=following_count
        )

    # Continue with your existing code...
    @app.route('/follow/<int:user_id>', methods=['POST'])
    @login_required
    def toggle_follow(user_id):
        person = db.session.get(User, user_id)

        if person is None:
            abort(404)

        if person.id == current_user.id:
            abort(400)

        return_to = request.form.get('return_to', 'profile')

        if return_to == 'people':
            destination = url_for('people')
        else:
            destination = url_for('profile', username=person.Username)

        existing_follow = Follow.query.filter_by(
            follower_id=current_user.id,
            following_id=person.id
        ).first()

        if existing_follow:
            db.session.delete(existing_follow)
            flash('You have unfollowed this user.')

        else:
            new_follow = Follow(
                follower_id=current_user.id,
                following_id=person.id,
                date=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )

            new_notification = Notification(
                recipient_id=person.id,
                actor_id=current_user.id,
                notification_type='follow',
                date=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )

            db.session.add(new_follow)
            db.session.add(new_notification)

            flash('You are now following this user.')

        db.session.commit()

        return redirect(destination)



    @app.route('/notifications')
    @login_required
    def notifications():
        notifications = db.session.query(Notification, User).join(
            User, Notification.actor_id == User.id
        ).filter(
            Notification.recipient_id == current_user.id
        ).order_by(
            Notification.id.desc()
        ).all()

        return render_template(
            'notification.html',
            notifications=notifications
        )


    @app.route('/notifications/mark-all-read', methods=['POST'])
    @login_required
    def mark_all_notifications_read():

        # Get only unread notifications belonging to the logged-in user
        unread_notifications = Notification.query.filter_by(
            recipient_id=current_user.id,
            is_read=False
        ).all()

        if unread_notifications:

            # Mark each unread notification as read
            for notification in unread_notifications:
                notification.is_read = True

            db.session.commit()

            flash('All notifications have been marked as read.')

        else:
            flash('You have no unread notifications.')

        return redirect(url_for('notifications'))


    @app.route('/post/<int:id>/comment', methods=['POST'])
    @login_required
    def add_comment(id):
        post = db.session.get(Post, id)

        if post is None or not post.published or post.status != "Active":
            abort(404)

        # Decide where to return after submitting the comment.
        return_to = request.form.get('return_to', 'published')

        if return_to == 'profile':
            author = db.session.get(User, post.user_id)
            destination = url_for('profile', username=author.Username)
        else:
            destination = url_for('published_posts')

        content = request.form.get('content', '').strip()

        if not content:
            flash('Please enter a comment.')
            return redirect(destination)

        if len(content) > 2000:
            flash('Comments cannot exceed 2000 characters.')
            return redirect(destination)

        comment = Comment(
            content=content,
            post_id=post.id,
            user_id=current_user.id,
            date=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )

        db.session.add(comment)
        db.session.commit()

        flash('Comment added successfully.')
        return redirect(destination)



    @app.route('/post/<int:id>/like', methods=['POST'])
    @login_required
    def toggle_like(id):
        post = db.session.get(Post, id)

        if post is None or not post.published or post.status != "Active":
            abort(404)

        # Decide where to return after liking or unliking.
        return_to = request.form.get('return_to', 'published')

        if return_to == 'profile':
            author = db.session.get(User, post.user_id)
            destination = url_for('profile', username=author.Username)
        else:
            destination = url_for('published_posts')

        existing_like = Like.query.filter_by(
            post_id=post.id,
            user_id=current_user.id
        ).first()

        try:
            if existing_like:
                db.session.delete(existing_like)
            else:
                new_like = Like(
                    post_id=post.id,
                    user_id=current_user.id
                )
                db.session.add(new_like)

            db.session.commit()

        except Exception as error:
            db.session.rollback()
            print("LIKE ERROR:", repr(error))
            raise

        return redirect(destination)


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

        # Find the post using its ID.
        post = db.session.get(Post, id)

        # Stop access if the post does not exist
        # or does not belong to the logged-in user.
        if post is None or post.user_id != current_user.id:
            abort(404)

        # Update the post when the form is submitted.
        if request.method == 'POST':

            post.title = request.form['title']
            post.description = request.form['description']

            file = request.files.get('post_image')

            if file and file.filename != '' and allowed_file(file.filename):

                filename = secure_filename(file.filename)

                file.save(
                    os.path.join(app.config['UPLOAD_FOLDER'], filename)
                )

                post.upload = filename

            db.session.commit()

            flash('Post updated successfully.')

            return redirect(url_for('home'))

        # Display the edit page.
        return render_template('edit.html', edit=post)

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
    def published_posts():

        # Get all active, published posts and their authors.
        rows = db.session.execute(
            db.select(Post, User)
            .join(User, Post.user_id == User.id)
            .where(
                Post.published == True,
                Post.status == "Active"
            )
            .order_by(Post.date.desc())
        ).all()

        # Get the IDs of posts displayed in the feed.
        post_ids = [post.id for post, author in rows]

        # Retrieve comments belonging to these posts.
        if post_ids:
            comments = Comment.query.filter(
                Comment.post_id.in_(post_ids)
            ).all()
        else:
            comments = []

        # Get usernames for displaying comment authors.
        comment_user_ids = {comment.user_id for comment in comments}

        users = User.query.filter(
            User.id.in_(comment_user_ids)
        ).all() if comment_user_ids else []

        comment_usernames = {
            user.id: user.Username for user in users
        }

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

        # Only check liked posts when a user is logged in.
        liked_post_ids = set()

        if current_user.is_authenticated and post_ids:

            liked_post_ids = set(
                db.session.execute(
                    db.select(Like.post_id).where(
                        Like.user_id == current_user.id,
                        Like.post_id.in_(post_ids)
                    )
                ).scalars().all()
            )

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

    @app.route('/dashboard', methods=['GET', 'POST'])
    @login_required
    def home():

        filename = None 


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


    @app.route('/')
    def landing():

        # Get the four most recently published active events.
        latest_events = db.session.execute(
            db.select(Post, User)
            .join(User, Post.user_id == User.id)
            .where(
                Post.published == True,
                Post.status == "Active"
            )
            .order_by(Post.date.desc())
            .limit(4)
        ).all()

        return render_template(
            'landing.html',
            latest_events=latest_events
        )

    
    # @app.route('/dashboard')
    # @login_required
    # def dashboard():
    #     return render_template('index.html', user=current_user)

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))
    
    with app.app_context():
        db.create_all()

        # print("ACTIVE DATABASE:", db.engine.url.database)
        # print("ABSOLUTE PATH:", db.engine.url)

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)