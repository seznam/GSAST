from typing import Optional


class BaseRepository:
    """Standardized repository information"""
    
    def __init__(self, **kwargs):
        self.name = kwargs.get('name', '')
        self.full_name = kwargs.get('full_name', '')
        self.description = kwargs.get('description', '')
        self.clone_url = kwargs.get('clone_url', '')
        self.ssh_url = kwargs.get('ssh_url', '')
        self.web_url = kwargs.get('web_url', '')
        self.size_mb = kwargs.get('size_mb', 0)
        self.stars = kwargs.get('stars', 0)
        self.forks = kwargs.get('forks', 0)
        self.language = kwargs.get('language', '')
        self.archived = kwargs.get('archived', False)
        self.is_fork = kwargs.get('is_fork', False)
        self.last_activity = kwargs.get('last_activity')
        self.created_at = kwargs.get('created_at')
        self.owner = kwargs.get('owner', '')
        self.private = kwargs.get('private', False)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            'name': self.name,
            'full_name': self.full_name,
            'description': self.description,
            'clone_url': self.clone_url,
            'ssh_url': self.ssh_url,
            'web_url': self.web_url,
            'size_mb': self.size_mb,
            'stars': self.stars,
            'forks': self.forks,
            'language': self.language,
            'archived': self.archived,
            'is_fork': self.is_fork,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'owner': self.owner,
            'private': self.private
        }
    
    def __str__(self):
        return f"BaseRepository(name={self.name}, full_name={self.full_name}, description={self.description}, clone_url={self.clone_url}, ssh_url={self.ssh_url}, web_url={self.web_url}, size_mb={self.size_mb}, stars={self.stars}, forks={self.forks}, language={self.language}, archived={self.archived}, is_fork={self.is_fork}, last_activity={self.last_activity}, created_at={self.created_at}, owner={self.owner}, private={self.private})"