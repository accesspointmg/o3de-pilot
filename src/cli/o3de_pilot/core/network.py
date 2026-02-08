# O3DE Pilot - Network Connectivity
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Network connectivity detection and management.

Provides a way to check if internet is accessible and track online/offline status.
When offline, the application should use cached data and disable network operations.
"""

import socket
import threading
import time
import logging
from typing import Callable, Optional
from functools import lru_cache

logger = logging.getLogger("o3de_pilot.network")


# Default hosts to check for connectivity
# Using well-known DNS servers that should always be available
CONNECTIVITY_HOSTS = [
    ("8.8.8.8", 53),     # Google DNS
    ("1.1.1.1", 53),     # Cloudflare DNS
    ("208.67.222.222", 53),  # OpenDNS
]

# Timeout for connectivity check (seconds)
CONNECTIVITY_TIMEOUT = 3.0

# Cache duration for connectivity check (seconds)
CONNECTIVITY_CACHE_DURATION = 10.0


class NetworkStatus:
    """
    Singleton class for tracking network connectivity status.
    
    Usage:
        # Check current status
        if NetworkStatus.is_online():
            # Do network operation
            pass
        
        # Register callback for status changes
        def on_status_change(is_online: bool):
            print(f"Network is now {'online' if is_online else 'offline'}")
        
        NetworkStatus.add_listener(on_status_change)
        
        # Start monitoring (in background thread)
        NetworkStatus.start_monitoring()
    """
    
    _online: bool = True  # Assume online until proven otherwise
    _last_check: float = 0.0
    _listeners: list[Callable[[bool], None]] = []
    _monitoring: bool = False
    _monitor_thread: Optional[threading.Thread] = None
    _stop_monitoring: bool = False
    _lock = threading.Lock()
    
    @classmethod
    def _check_connectivity(cls, timeout: float = CONNECTIVITY_TIMEOUT) -> bool:
        """
        Check if internet is accessible by attempting to connect to known hosts.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            True if any host is reachable, False otherwise
        """
        for host, port in CONNECTIVITY_HOSTS:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    logger.debug(f"Connected to {host}:{port} - network is online")
                    return True
                    
            except socket.error as e:
                logger.debug(f"Failed to connect to {host}:{port}: {e}")
                continue
        
        logger.debug("All connectivity hosts unreachable - network is offline")
        return False
    
    @classmethod
    def is_online(cls, force_check: bool = False) -> bool:
        """
        Check if the network is online.
        
        Uses cached result unless force_check is True or cache has expired.
        
        Args:
            force_check: If True, always perform a fresh connectivity check
            
        Returns:
            True if online, False if offline
        """
        current_time = time.time()
        
        with cls._lock:
            # Check if we need to refresh the status
            if force_check or (current_time - cls._last_check) > CONNECTIVITY_CACHE_DURATION:
                old_status = cls._online
                cls._online = cls._check_connectivity()
                cls._last_check = current_time
                
                # Notify listeners if status changed
                if old_status != cls._online:
                    cls._notify_listeners()
            
            return cls._online
    
    @classmethod
    def is_offline(cls, force_check: bool = False) -> bool:
        """Convenience method - opposite of is_online()."""
        return not cls.is_online(force_check)
    
    @classmethod
    def add_listener(cls, callback: Callable[[bool], None]) -> None:
        """
        Add a listener to be notified of connectivity status changes.
        
        Args:
            callback: Function that takes a bool (True = online, False = offline)
        """
        with cls._lock:
            if callback not in cls._listeners:
                cls._listeners.append(callback)
    
    @classmethod
    def remove_listener(cls, callback: Callable[[bool], None]) -> None:
        """Remove a previously added listener."""
        with cls._lock:
            if callback in cls._listeners:
                cls._listeners.remove(callback)
    
    @classmethod
    def _notify_listeners(cls) -> None:
        """Notify all listeners of current status. Must be called with lock held."""
        status = cls._online
        for listener in cls._listeners:
            try:
                listener(status)
            except Exception as e:
                logger.error(f"Error in network status listener: {e}")
    
    @classmethod
    def start_monitoring(cls, interval_seconds: float = 30.0) -> None:
        """
        Start background monitoring of network status.
        
        Args:
            interval_seconds: How often to check connectivity
        """
        with cls._lock:
            if cls._monitoring:
                return
            
            cls._monitoring = True
            cls._stop_monitoring = False
            
            def monitor_loop():
                while not cls._stop_monitoring:
                    cls.is_online(force_check=True)
                    
                    # Sleep in small increments to allow stopping
                    for _ in range(int(interval_seconds * 10)):
                        if cls._stop_monitoring:
                            break
                        time.sleep(0.1)
                
                with cls._lock:
                    cls._monitoring = False
            
            cls._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
            cls._monitor_thread.start()
    
    @classmethod
    def stop_monitoring(cls) -> None:
        """Stop background monitoring."""
        cls._stop_monitoring = True
        if cls._monitor_thread:
            cls._monitor_thread.join(timeout=5.0)
            cls._monitor_thread = None
    
    @classmethod
    def set_offline_for_testing(cls, offline: bool = True) -> None:
        """
        Force offline status for testing purposes.
        
        Args:
            offline: If True, force offline; if False, restore to checking
        """
        with cls._lock:
            old_status = cls._online
            cls._online = not offline
            cls._last_check = time.time() + 3600  # Don't auto-refresh for an hour
            
            if old_status != cls._online:
                cls._notify_listeners()


def is_online(force_check: bool = False) -> bool:
    """
    Check if the network is online.
    
    Convenience function that delegates to NetworkStatus.is_online().
    
    Args:
        force_check: If True, force a fresh connectivity check
        
    Returns:
        True if online, False if offline
    """
    return NetworkStatus.is_online(force_check)


def is_offline(force_check: bool = False) -> bool:
    """Convenience function - opposite of is_online()."""
    return not is_online(force_check)
