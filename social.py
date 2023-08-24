from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr
from typing import Dict
from datetime import datetime, timedelta
from cachetools import TTLCache
import jwt

app = FastAPI()

db_users = {}
db_posts = {}
SECRET_KEY = "secure-secret-key"
CACHE_TTL = 300
CACHE_MAXSIZE = 1000

cache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL)

class Token(BaseModel):
    access_token: str

class User(BaseModel):
    email: EmailStr
    password: str

class Post(BaseModel):
    content: str

def create_token(email: str) -> str:
    expiry_time = datetime.utcnow() + timedelta(minutes=30)
    payload = {"sub": email, "exp": expiry_time}
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return token

def authenticate_authorization(authorization: str = Header(...)):
    try:
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except (jwt.DecodeError, IndexError):
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/register", response_model=Token)
async def register(user: User):
    db_users[user.email] = user
    token = create_token(user.email)
    return Token(access_token=token)

@app.post("/authenticate", response_model=Token)
async def authenticate(user: User):
    if user.email in db_users and db_users[user.email].password == user.password:
        token = create_token(user.email)
        return Token(access_token=token)
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/createPost")
async def create_post(post: Post, current_user: Dict = Depends(authenticate_authorization)):
    if len(post.content.encode()) > 1024 * 1024:
        raise HTTPException(status_code=400, detail="Payload too large")
    post_id = len(db_posts) + 1
    db_posts[post_id] = {"content": post.content, "author": current_user['sub']}
    return {"postID": post_id}

@app.get("/fetchPosts")
async def fetch_posts(current_user: Dict = Depends(authenticate_authorization)):
    cached_posts = cache.get(current_user["sub"])
    if cached_posts:
        return cached_posts
    posts = [{"postID": p_id, **p} for p_id, p in db_posts.items() if p["author"] == current_user['sub']]
    cache[current_user['sub']] = posts
    return posts

@app.delete("/removePost")
async def remove_post(post_id: int, current_user: Dict = Depends(authenticate_authorization)):
    if post_id in db_posts and db_posts[post_id]["author"] == current_user['sub']:
        del db_posts[post_id]
        return {"message": "Post deleted"}
    raise HTTPException(status_code=404, detail="Post not found or unauthorized")
