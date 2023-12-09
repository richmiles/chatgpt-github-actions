# Automated Code Review using the ChatGPT language model

## Import statements
import argparse
import string
from xml.etree.ElementInclude import include
from xmlrpc.client import boolean
import openai
import os
import requests
from github import Github

## Adding command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument("--openai_api_key", help="Your OpenAI API Key")
parser.add_argument("--github_token", help="Your Github Token")
parser.add_argument("--github_pr_id", help="Your Github PR ID")
parser.add_argument(
    "--openai_engine",
    default="gpt-3.5-turbo",
    help="GPT Chat Completions model to use. Options: gpt-4, gpt-4 turbo, gpt-3.5-turbo",
)
parser.add_argument(
    "--openai_temperature",
    default=0.5,
    help="Sampling temperature to use. Higher values means the model will take more risks. Recommended: 0.5",
)
parser.add_argument(
    "--openai_max_tokens",
    default=2048,
    help="The maximum number of tokens to generate in the completion.",
)
parser.add_argument(
    "--mode", default="files", help="PR interpretation form. Options: files, patch"
)
parser.add_argument(
    "--included_file_extensions", default="", help="A | delimited list of file extensions to include. e.g. cs|js|..."
)
parser.add_argument(
    "--excluded_file_extensions", default="", help="A | delimited list of file extensions to exclude. e.g. cs|js|..."
)
parser.add_argument(
    "--include_tokens_in_output", default="false", help="True will include token cost in comment."
)
args = parser.parse_args()

## Authenticating with the OpenAI API
openai.api_key = args.openai_api_key

## Authenticating with the Github API
g = Github(args.github_token)


def files(included_file_extensions: list[str], 
          excluded_file_extensions: list[str], 
          include_tokens_in_output: bool) -> None:
    
    repo = g.get_repo(os.getenv("GITHUB_REPOSITORY"))
    pull_request = repo.get_pull(int(args.github_pr_id))

    ## Loop through the commits in the pull request
    commits = pull_request.get_commits()
    for commit in commits:
        # Getting the modified files in the commit
        files = commit.files
        for file in files:
            # Getting the file name and content
            file_name = file.filename
            if determine_if_file_is_include(file_name, included_file_extensions, excluded_file_extensions) == False:
                continue
            
            try:
                content = repo.get_contents(
                    file_name, ref=commit.sha
                ).decoded_content.decode("utf-8")

                review = get_code_review_from_openai(content, include_tokens_in_output)

                # Adding a comment to the pull request with ChatGPT's response
                pull_request.create_issue_comment(
                    f"ChatGPT's response about `{file_name}`:\n {review}"
                )
            except Exception as e:
                error_message = str(e)
                print(error_message)
                pull_request.create_issue_comment(error_message)
                raise e


def patch(included_file_extensions: list[str], 
          excluded_file_extensions: list[str], 
          include_tokens_in_output: bool) -> None:
    repo = g.get_repo(os.getenv("GITHUB_REPOSITORY"))
    pull_request = repo.get_pull(int(args.github_pr_id))

    content = get_content_patch()

    if len(content) == 0:
        pull_request.create_issue_comment(f"Patch file does not contain any changes")
        return

    parsed_text = content.split("diff")

    for diff_text in parsed_text:
        if len(diff_text) == 0:
            continue

        try:
            file_name = diff_text.split("b/")[1].splitlines()[0]

            if determine_if_file_is_include(file_name, included_file_extensions, excluded_file_extensions) == False:
                continue

            review = get_code_review_from_openai(diff_text, include_tokens_in_output)
            # Adding a comment to the pull request with ChatGPT's response
            pull_request.create_issue_comment(
                f"ChatGPT's response about `{file_name}`:\n {review}"
            )
        except Exception as e:
            error_message = str(e)
            print(error_message)
            pull_request.create_issue_comment(error_message)
            raise e


def get_content_patch() -> str:
    url = f"https://api.github.com/repos/{os.getenv('GITHUB_REPOSITORY')}/pulls/{args.github_pr_id}"
    print(url)

    headers = {
        "Authorization": f"token {args.github_token}",
        "Accept": "application/vnd.github.v3.diff",
    }

    response = requests.request("GET", url, headers=headers)

    if response.status_code != 200:
        raise Exception(response.text)

    return response.text


def get_code_review_from_openai(content: str, include_tokens_in_output: bool) -> str:
    try:
        messages = [
            {
                "role": "system",
                "content": "Please review the following code for clarity, efficiency, and adherence to best practices. Highlight any areas for improvement, suggest optimizations, and note potential bugs or security vulnerabilities. Also, consider the maintainability and scalability of the code.",
            },
            {"role": "user", "content": content},
        ]
        # Updated code to use ChatGPT completions
        response = openai.chat.completions.create(
            model=args.openai_engine,
            messages=messages,
            temperature=float(args.openai_temperature),
            max_tokens=int(args.openai_max_tokens),
        )

        # Accessing the completion text from the response
        completion_text = (
            response.choices[0].message.content if response.choices else ""
        )
        if(include_tokens_in_output):
            completion_text += f"\n\n*Completion Tokens:* **{response.usage.completion_tokens}**" if response.usage else ""
            completion_text += f"\n*Prompt Tokens:* **{response.usage.prompt_tokens}**" if response.usage else ""
            
        return completion_text
    except openai.error.BadRequestError as e:
        # Handle specific bad request errors here
        error_message = str(e)
        raise Exception(
            f"BadRequestError occurred: {error_message}"
        )
    except Exception as e:
        error_message = str(e)
        error_details = f"Details: `{error_message}`\nContext: `{content}`\nMessages: `{messages}`"
        raise Exception(
            f"ChatGPT encountered an issue processing your request.\n\n{error_details}"
        )
    
def determine_if_file_is_include(file_name: str, included_file_extensions: list[str], excluded_file_extensions: list[str]) -> bool:
    if len(included_file_extensions) > 0:
        if file_name.index(".") == -1 and "" not in included_file_extensions:
            return False
        if file_name.split(".")[-1] not in included_file_extensions:
            return False
    if len(excluded_file_extensions) > 0:
        if file_name.index(".") == -1 and "" in excluded_file_extensions:
            return False
        if file_name.split(".")[-1] in excluded_file_extensions:
            return False
    return True

def parse_bool(value):
    return value.lower() in ['true', '1', 't', 'y', 'yes']

# if args.include_tokens_in_output != "" split on | and create an array of the tokens
included_file_extensions = args.included_file_extensions.split("|") if args.included_file_extensions != "" else []
excluded_file_extensions = args.excluded_file_extensions.split("|") if args.excluded_file_extensions != "" else []
include_tokens_in_output = parse_bool(args.include_tokens_in_output)

if args.mode == "files":
    files(included_file_extensions, excluded_file_extensions, include_tokens_in_output)

if args.mode == "patch":
    patch(included_file_extensions, excluded_file_extensions, include_tokens_in_output)