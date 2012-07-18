# ZYNC Plugin for Autodesk's Maya

## Installing

Everything you need is included in this repository. You'll just need to point Maya to this folder to load it on startup.

The easiest way to do this is to create a Maya.env file and point it to this folder. See included Maya.env.example for an example of how to do this.

Your Maya.env will need to set the following two variables:

```
PYTHONPATH = Z:/path/to/plugins
XBMLANGPATH = Z:/path/to/plugins
```

Be careful; if Maya.env already exists it may be setting these variables already. If you see them elsewhere in the file, you'll need to append your path to the existing setting. For example:

PYTHONPATH = C:/my/scripts/folder;Z:/path/to/plugins

To separate paths, use a semicolon (;) on Windows and a colon (:) on Linux and Mac OS X.

For more information on setting up a Maya.env file, see the page "Setting environment variables using Maya.env" in the Maya Help Docs.

Now, open up maya_zync_submit/zync_submit.py. Near the top you'll see a few lines tell you to REPLACE the values with your own. Edit those lines accordingly.

For the line that says "# REPLACE WITH PATH TO zync/ DIRECTORY", its talking about the "zync" folder included with these plugins. This folder contains the Python API used by both the Nuke and Maya plugins, and should be stored in a central place.
