"""
GitHub-specific models for the connector.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl


class GitHubUser(BaseModel):
    """GitHub user model."""

    login: str = Field(..., description="User login")
    id: int = Field(..., description="User ID")
    node_id: str = Field(..., description="Node ID")
    avatar_url: HttpUrl = Field(..., description="Avatar URL")
    gravatar_id: Optional[str] = Field(default=None, description="Gravatar ID")
    url: HttpUrl = Field(..., description="User URL")
    html_url: HttpUrl = Field(..., description="HTML URL")
    followers_url: HttpUrl = Field(..., description="Followers URL")
    following_url: HttpUrl = Field(..., description="Following URL")
    gists_url: HttpUrl = Field(..., description="Gists URL")
    starred_url: HttpUrl = Field(..., description="Starred URL")
    subscriptions_url: HttpUrl = Field(..., description="Subscriptions URL")
    organizations_url: HttpUrl = Field(..., description="Organizations URL")
    repos_url: HttpUrl = Field(..., description="Repositories URL")
    events_url: HttpUrl = Field(..., description="Events URL")
    received_events_url: HttpUrl = Field(..., description="Received events URL")
    type: str = Field(..., description="User type")
    site_admin: bool = Field(default=False, description="Site admin")
    name: Optional[str] = Field(default=None, description="Full name")
    company: Optional[str] = Field(default=None, description="Company")
    blog: Optional[str] = Field(default=None, description="Blog URL")
    location: Optional[str] = Field(default=None, description="Location")
    email: Optional[str] = Field(default=None, description="Email")
    hireable: Optional[bool] = Field(default=None, description="Hireable")
    bio: Optional[str] = Field(default=None, description="Bio")
    twitter_username: Optional[str] = Field(default=None, description="Twitter username")
    public_repos: int = Field(default=0, description="Public repositories count")
    public_gists: int = Field(default=0, description="Public gists count")
    followers: int = Field(default=0, description="Followers count")
    following: int = Field(default=0, description="Following count")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Update timestamp")


class GitHubLicense(BaseModel):
    """GitHub license model."""

    key: str = Field(..., description="License key")
    name: str = Field(..., description="License name")
    spdx_id: str = Field(..., description="SPDX ID")
    url: Optional[HttpUrl] = Field(default=None, description="License URL")
    node_id: str = Field(..., description="Node ID")


class GitHubRepository(BaseModel):
    """GitHub repository model."""

    id: int = Field(..., description="Repository ID")
    node_id: str = Field(..., description="Node ID")
    name: str = Field(..., description="Repository name")
    full_name: str = Field(..., description="Full name (owner/repo)")
    private: bool = Field(default=False, description="Is private")
    owner: GitHubUser = Field(..., description="Repository owner")
    html_url: HttpUrl = Field(..., description="HTML URL")
    description: Optional[str] = Field(default=None, description="Description")
    fork: bool = Field(default=False, description="Is fork")
    url: HttpUrl = Field(..., description="API URL")
    forks_url: HttpUrl = Field(..., description="Forks URL")
    keys_url: HttpUrl = Field(..., description="Keys URL")
    collaborators_url: HttpUrl = Field(..., description="Collaborators URL")
    teams_url: HttpUrl = Field(..., description="Teams URL")
    hooks_url: HttpUrl = Field(..., description="Hooks URL")
    issue_events_url: HttpUrl = Field(..., description="Issue events URL")
    events_url: HttpUrl = Field(..., description="Events URL")
    assignees_url: HttpUrl = Field(..., description="Assignees URL")
    branches_url: HttpUrl = Field(..., description="Branches URL")
    tags_url: HttpUrl = Field(..., description="Tags URL")
    blobs_url: HttpUrl = Field(..., description="Blobs URL")
    git_tags_url: HttpUrl = Field(..., description="Git tags URL")
    git_refs_url: HttpUrl = Field(..., description="Git refs URL")
    trees_url: HttpUrl = Field(..., description="Trees URL")
    statuses_url: HttpUrl = Field(..., description="Statuses URL")
    languages_url: HttpUrl = Field(..., description="Languages URL")
    stargazers_url: HttpUrl = Field(..., description="Stargazers URL")
    contributors_url: HttpUrl = Field(..., description="Contributors URL")
    subscribers_url: HttpUrl = Field(..., description="Subscribers URL")
    subscription_url: HttpUrl = Field(..., description="Subscription URL")
    commits_url: HttpUrl = Field(..., description="Commits URL")
    git_commits_url: HttpUrl = Field(..., description="Git commits URL")
    comments_url: HttpUrl = Field(..., description="Comments URL")
    issue_comment_url: HttpUrl = Field(..., description="Issue comment URL")
    contents_url: HttpUrl = Field(..., description="Contents URL")
    compare_url: HttpUrl = Field(..., description="Compare URL")
    merges_url: HttpUrl = Field(..., description="Merges URL")
    archive_url: HttpUrl = Field(..., description="Archive URL")
    downloads_url: HttpUrl = Field(..., description="Downloads URL")
    issues_url: HttpUrl = Field(..., description="Issues URL")
    pulls_url: HttpUrl = Field(..., description="Pulls URL")
    milestones_url: HttpUrl = Field(..., description="Milestones URL")
    notifications_url: HttpUrl = Field(..., description="Notifications URL")
    labels_url: HttpUrl = Field(..., description="Labels URL")
    releases_url: HttpUrl = Field(..., description="Releases URL")
    deployments_url: HttpUrl = Field(..., description="Deployments URL")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Update timestamp")
    pushed_at: datetime = Field(..., description="Last push timestamp")
    git_url: str = Field(..., description="Git URL")
    ssh_url: str = Field(..., description="SSH URL")
    clone_url: HttpUrl = Field(..., description="Clone URL")
    svn_url: HttpUrl = Field(..., description="SVN URL")
    homepage: Optional[HttpUrl] = Field(default=None, description="Homepage")
    size: int = Field(default=0, description="Size in KB")
    stargazers_count: int = Field(default=0, description="Stars count")
    watchers_count: int = Field(default=0, description="Watchers count")
    language: Optional[str] = Field(default=None, description="Primary language")
    has_issues: bool = Field(default=False, description="Has issues enabled")
    has_projects: bool = Field(default=False, description="Has projects enabled")
    has_downloads: bool = Field(default=False, description="Has downloads enabled")
    has_wiki: bool = Field(default=False, description="Has wiki enabled")
    has_pages: bool = Field(default=False, description="Has pages enabled")
    has_discussions: bool = Field(default=False, description="Has discussions enabled")
    forks_count: int = Field(default=0, description="Forks count")
    mirror_url: Optional[HttpUrl] = Field(default=None, description="Mirror URL")
    archived: bool = Field(default=False, description="Is archived")
    disabled: bool = Field(default=False, description="Is disabled")
    open_issues_count: int = Field(default=0, description="Open issues count")
    license: Optional[GitHubLicense] = Field(default=None, description="License")
    allow_forking: bool = Field(default=True, description="Allow forking")
    is_template: bool = Field(default=False, description="Is template")
    web_commit_signoff_required: bool = Field(default=False, description="Web commit signoff required")
    topics: List[str] = Field(default_factory=list, description="Repository topics")
    visibility: str = Field(default="public", description="Visibility")
    forks: int = Field(default=0, description="Forks count")
    open_issues: int = Field(default=0, description="Open issues count")
    watchers: int = Field(default=0, description="Watchers count")
    default_branch: str = Field(..., description="Default branch")


class GitHubAsset(BaseModel):
    """GitHub release asset model."""

    url: HttpUrl = Field(..., description="Asset API URL")
    browser_download_url: HttpUrl = Field(..., description="Browser download URL")
    id: int = Field(..., description="Asset ID")
    node_id: str = Field(..., description="Node ID")
    name: str = Field(..., description="Asset name")
    label: Optional[str] = Field(default=None, description="Asset label")
    state: str = Field(..., description="Asset state")
    content_type: str = Field(..., description="Content type")
    size: int = Field(..., description="Size in bytes")
    download_count: int = Field(default=0, description="Download count")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Update timestamp")
    uploader: Optional[GitHubUser] = Field(default=None, description="Uploader")


class GitHubRelease(BaseModel):
    """GitHub release model."""

    url: HttpUrl = Field(..., description="Release API URL")
    html_url: HttpUrl = Field(..., description="Release HTML URL")
    assets_url: HttpUrl = Field(..., description="Assets URL")
    upload_url: str = Field(..., description="Upload URL")
    tarball_url: Optional[HttpUrl] = Field(default=None, description="Tarball URL")
    zipball_url: Optional[HttpUrl] = Field(default=None, description="Zipball URL")
    id: int = Field(..., description="Release ID")
    node_id: str = Field(..., description="Node ID")
    tag_name: str = Field(..., description="Tag name")
    target_commitish: str = Field(..., description="Target commitish")
    name: Optional[str] = Field(default=None, description="Release name")
    body: Optional[str] = Field(default=None, description="Release body")
    draft: bool = Field(default=False, description="Is draft")
    prerelease: bool = Field(default=False, description="Is prerelease")
    created_at: datetime = Field(..., description="Creation timestamp")
    published_at: datetime = Field(..., description="Publication timestamp")
    author: Optional[GitHubUser] = Field(default=None, description="Author")
    assets: List[GitHubAsset] = Field(default_factory=list, description="Release assets")


class GitHubSearchResult(BaseModel):
    """GitHub search result model."""

    total_count: int = Field(..., description="Total count")
    incomplete_results: bool = Field(default=False, description="Incomplete results")
    items: List[GitHubRepository] = Field(default_factory=list, description="Repository items")
