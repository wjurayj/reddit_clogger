import openai
import praw
import asyncio
from typing import Any
from functools import wraps

openai.api_base = """<LOCAL URL HOSTING INSTRUCT-TUNED LLM>"""

#You will need to make a reddit app for this--see more info here https://www.reddit.com/prefs/apps/
CLIENT_ID = '<YOUR-CLIENT-ID>'
CLIENT_SECRET = '<YOUR-CLIENT-SECRET>'
USERNAME = '<YOUR-REDDIT-USERNAME>'
PASSWORD = '<YOUR-REDDIT-PASSWORD>'

#Note--many subreddits have account age/karma requirements to post comments
SUBREDDIT = 'politics'

reddit = praw.Reddit(
    user_agent="clogger",
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    username=USERNAME,
    password=PASSWORD,
)

# Prompt for determining, from a submission's title, whether to look through its comments 
THREAD_INTEREST_PROMPT = """
Act as a perceptive social media manager. Based on the title of a thread, report whether\
 it seems certain to discuss the US Supreme Court, or any of its members.
Your response should be a single word, either 'Yes' or 'No', and nothing more.
Title: {}
Prediction:
""".strip()

# Prompt for determining, from a comment, whether we 
COMMENT_INTEREST_PROMPT = """
Act as a perceptive political analyst, and discern whether a given comment discusses ethics,\
 corruption, congressional oversight, or checks and balances.
Your response should be a single word, either 'Yes' or 'No', and nothing more.
Comment: {}
Prediction:
""".strip()

COMMENT_REPLY_PROMPT = """
Act as a well-informed and personable Reddit user. You want people to know that Congress has\
 the constitutional power and duty to regulate the judiciary, and that this is likely a rare\
 issue with bipartisan consensus. Your responses should be in the informal style of a social\
 media comment, and thus quite short and to the point, no more than 2 sentences and\
 generally less, while matching the general emotional tone of the user you are replying to.\
 You should respond to what the user seems concerned with, without directly addressing or\
 repeating the user. You should encourage them to write to their Congressional Representative\
 and their Senators.
Your response should contain only the content that should be posted in the reply, and nothing more.

Comment: {}
Response:
""".strip()


# Restructures a comment into a dict 
def extract_comment_data(comment):
    return {
        'id': comment.id,
        'author': comment.author.name if comment.author else "[deleted]",
        'timestamp': comment.created_utc,
        'body': comment.body,
    }

# Useful for flattening a comment into a 
def extract_comment_data_with_parent(comment, parent_id=None):
    keys = ['id', 'author', 'timestamp', 'body', 'depth']
    ret = {k:comment[k] for k in keys}
    if parent_id:
        ret['parent_id'] = parent_id
    return ret

# To build a dictionary out of a Reddit comment object, maintaining the thread structure
def build_comment_tree(comment, depth=0):
    comment_data = extract_comment_data(comment)
    comment_data['depth'] = depth
    comment_data['replies'] = []

    for reply in comment.replies:
        reply_tree = build_comment_tree(reply, depth + 1)
        comment_data['replies'].append(reply_tree)

    return comment_data

# To build a dictionary out of the responses to a Reddit submission/thread
def get_submission_comment_tree(submission_id):
    submission = reddit.submission(id=submission_id)
    submission.comment_sort = 'top'
    submission.comments.replace_more(limit=None)
    
    comment_tree = []
    for top_level_comment in submission.comments:
        comment_tree.append(build_comment_tree(top_level_comment, 3))
    
    return comment_tree

# To turn a comment tree (as constructed above) into a simple list of comments, while maintaining info on each comment's parent
def flatten_comment_tree(comment_tree, parent_id=None):
    flattened_comments = []

    for comment_data in comment_tree:
        current_comment = extract_comment_data_with_parent(comment_data, parent_id)
        flattened_comments.append(current_comment)

        if comment_data['replies']:
            flattened_replies = flatten_comment_tree(comment_data['replies'], comment_data['id'])
            flattened_comments.extend(flattened_replies)

    return flattened_comments

# Utility function to turn a prompt into a well-formatted argument to openai.ChatCompletion
def wrap_message(message):
    messages = [{
        'role':'user',
        'content':message
    }]
    return messages

# Posts a reply to a reddit comment 
def post_reply(comment_id, reply_text):
    comment = reddit.comment(id=comment_id)
    comment.reply(reply_text)

class TooManyTriesException(Exception):
    pass

# Helper function to wait, then retry when a rate limit error is expected
def async_retry(attempts, delay=5):
    def func_wrapper(f):
        @wraps(f)
        async def wrapper(*args, **kwargs):
            for attempt in range(attempts):
                try:
                    return await f(*args, **kwargs)
                except Exception as exc:
                    print(f"Exception for {f} on try {attempt}")
                    if attempt == attempts - 1:
                        raise TooManyTriesException() from exc
                    await asyncio.sleep(delay)  # Adjust the sleep duration as needed
        return wrapper
    return func_wrapper

# Wrapper for ChatCompletion, to enable retry logic
@async_retry(attempts=3, delay=5)
async def retry_chatcompletion(**kwargs):
    response = await openai.ChatCompletion.acreate(
        **kwargs
    )
    return response

# Allows a list of prompts to be sent to the OpenAI ChatCompletion endpoint concurrently
async def dispatch_openai_requests(
    messages_list: list[list[dict[str,Any]]],
    model: str = 'gpt-3.5-turbo',
    temperature: float = 1,
    max_tokens: int = 256,
    top_p: float = 1,
    frequency_penalty: float = 0,
    presence_penalty: float = 0,
) -> list[str]:
    """Dispatches requests to OpenAI API asynchronously.

    Args:
        messages_list: List of messages to be sent to OpenAI ChatCompletion API.
        model: OpenAI model to use.
        temperature: Temperature to use for the model.
        max_tokens: Maximum number of tokens to generate.
        top_p: Top p to use for the model.
    Returns:
        List of responses from OpenAI API.
    """
    async_responses = [
        retry_chatcompletion(
        # openai.ChatCompletion.acreate(
            model=model,
            messages=x,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
        )
        for x in messages_list
    ]
    return await asyncio.gather(*async_responses)

async def main():
    test = True

    # Gathering threads from a subreddit
    subreddit = reddit.subreddit(SUBREDDIT)   
    submissions = []
    for submission in subreddit.new(limit=50):
        submissions.append({
            'title':submission.title,
            'id':submission.id
        })
    
    print('\n\nThreads of interest:')
    # Filtering threads based on our topic of interest
    messages = [wrap_message(THREAD_INTEREST_PROMPT.format(sub['title'])) for sub in submissions]
    predictions = await dispatch_openai_requests(messages, max_tokens=3, temperature=0)
    threads_of_interest = []
    for i, x in enumerate(predictions):
        response = x['choices'][0]['message']['content']
        if 'yes' in response.lower().strip():
            threads_of_interest.append(submissions[i]['id'])
            if test:
                print(submissions[i]['title'])
                print('- - -')
    
    # Gathering comments from these threads
    comment_trees = {}
    comments = []
    for submission_id in threads_of_interest:
        comment_trees[submission_id] = get_submission_comment_tree(submission_id)
        comments.extend(flatten_comment_tree(comment_trees[submission_id]))
        
    # Filtering comments based on our topic of interest
    bot_accounts = {'automoderator', 'autotldr'} #extend with known bot accounts
    comments = [comment for comment in comments if not comment['author'].lower() in bot_accounts]
    
    messages = [wrap_message(COMMENT_INTEREST_PROMPT.format(comment['body'])) for comment in comments]
    predictions = await dispatch_openai_requests(messages, max_tokens=3, temperature=0)
    comments_of_interest = []
    for i, x in enumerate(predictions):
        response = x['choices'][0]['message']['content']
        if response.lower().split()[0] == 'yes':# == 'yes':
            comments_of_interest.append({
                'body':comments[i]['body'],
                'id':comments[i]['id'],
            })
    
    
    print('\n\nComments and replies:')

    # Generate responses to these comments
    messages = [wrap_message(COMMENT_REPLY_PROMPT.format(comment['body'])) for comment in comments_of_interest]
    replies = await dispatch_openai_requests(messages, max_tokens=256, temperature=0.7, frequency_penalty=2, presence_penalty=0.5)
    for i, x in enumerate(replies):
        response = x['choices'][0]['message']['content']
        if test:
            print(comments_of_interest[i]['body'])
            print('* * *')
            print(response)
            print('- - -')
        comments_of_interest[i]['reply'] = response
    
    # Post responses to Reddit
    if not test:
        for comment in comments_of_interest:
            print(f"COMMENT: {comment['body']}")
            print(f"REPLY: {comment['reply']}")
            if input('Enter a space and nothing more to approve this reply')[0] == ' ':
                post_reply(comment['id'], comment['reply'])
            asyncio.sleep(10) # To skirt auto-moderation
    
if __name__ == '__main__':
    asyncio.run(main())
