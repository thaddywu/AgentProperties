"""Recommendation Submission System — version 1.

A local, single-user application that records recommendation requests, tracks
registered recommendation-letter files, matches letters to requests, submits
them through an email gateway or a portal automation agent, and sends deadline
reminders.

The package is organized so that every external effect passes through
:mod:`recsub.policy`, which is the single enforcement point for the Safety
Policy.
"""

__version__ = "1.0.0"
