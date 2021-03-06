import os
import sys

import re
import subprocess
import shutil
from shlex import quote

from PyQt5.QtCore import QStandardPaths, QSettings
from PyQt5.QtWidgets import QApplication,  QWidget,  QMessageBox
import PyQt5.uic as uic
from PyQt5.QtXml import QDomDocument

try:
    import krita
    CONTEXT_KRITA = True
    Krita = Krita  # to stop Eric ide complaining about unknown Krita
    EXTENSION = krita.Extension

except ImportError:  # script being run in testing environment without Krita
    CONTEXT_KRITA = False
    EXTENSION = QWidget

TESTING=False

from .durradocumentkrita import DURRADocumentKrita


class DURRABackendExt(object):
    PREVIEW_SCALE = 0.5

    def __init__(self):
        self.durradocument = DURRADocumentKrita()
        self.workdir = ""

        self.output = ""

        self.script_abs_path = os.path.dirname(os.path.realpath(__file__))

    def setup(self):
        self.output = ""
        self.load()

    def _getWorkdir(self, filename_kra):
        if filename_kra != "":
            filename_path = os.path.dirname(os.path.realpath(filename_kra))
            work_filename_path = os.path.basename(
                os.path.normpath(filename_path))
            workdir = filename_path
            if work_filename_path == "work":
                workdir = os.path.dirname(os.path.realpath(filename_path))
            #workdir_basename = os.path.basename(os.path.normpath(workdir))
            return workdir

        return ""
    
    def load(self):
        if CONTEXT_KRITA:
            document = Krita.instance().activeDocument()
            if document:
                filename_kra = document.fileName()
                self.workdir = self._getWorkdir(filename_kra)
                status = self._gitStatus(self.workdir)
                if not status:
                    self.output = self.output + 'not a git repository (or any of the parent directories)' + "\n"
                else:
                    if TESTING:
                        self.output = self.output + status + "\n"

                self.durradocument.loadVersionFromWorkdir(self.workdir)
                self.durradocument.loadDocument(document)
    
    def save(self):
        if CONTEXT_KRITA:
            if self.durradocument.getKritaDocument():
                return self.durradocument.saveKritaDocument()
        return False

    def println(self, str):
        if str is not None:
            self.output = self.output + str + '\n'

    def makeMetaFiles(self):
        if not self.durradocument.getFilenameBaseName():
            self.println('filename is empty')
            return []

        files = self.durradocument.makeMetaFiles(self.workdir)

        return files
    
    def makeFiles(self):
        if not self.durradocument.getFilenameBaseName():
            self.println('filename is empty')
            return []

        files = self.durradocument.makeFiles(self.workdir)

        return files

    def runGit(self, workdir, files, msg, description=None, authorname=None, authoremail=None):
        output = ''

        output = output + self._gitAdd(workdir, files)
        output = output + self._gitCommit(workdir, msg, description, authorname, authoremail)

        return output

    def isWindows(self):
        return os.name == 'nt'

    def runCmd(self, cmd, workdir, silence=False):
        output = ''
        wd = os.getcwd()
        os.chdir(workdir)
        try:
            if self.isWindows():
                result = subprocess.run(' '.join(cmd), cwd=workdir, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if not silence:
                    output = output + '$ ' + ' '.join(cmd) + "\n"
                output = output + result.stdout.decode("latin")
                if not silence:
                    if(result.stderr):
                        self.println(result.stderr.decode("latin"))
                return output
            
            result = subprocess.run(' '.join(cmd), cwd=workdir, shell=True, capture_output=True)
            if not silence:
                output = output + '$ ' + ' '.join(cmd) + "\n"
            output = output + result.stdout.decode()
            if not silence:
                self.println(result.stderr.decode())
            return output
        except subprocess.CalledProcessError as err:
            output = output + "Error with Code " + err.returncode + "\n"
            if err.stdout:
                if not silence:
                    self.println(err.output.decode())
                output = output + err.stdout.decode() + "\n"
            if err.stderr:
                if not silence:
                    self.println(err.stderr.decode())
                output = output + 'Error: ' + err.stderr.decode() + "\n"
        finally:
            os.chdir(wd)


        return output

    def _gitStatus(self, workdir):
        cmd = ['git', 'status']
        output = self.runCmd(cmd, workdir)

        if not output:
            return False
        if output.find('not a git repository') >= 0:
            return False
        
        return output

    def gitIsRepo(self, workdir):
        cmd = ['git', 'status']
        output = self.runCmd(cmd, workdir, True)

        if not output:
            return False
        if output.find('not a git repository') >= 0:
            return False
        
        return True

    def _gitAdd(self, workdir, files):
        output = ''

        for file in files:
            if file:
                cmd = ['git', 'add ', quote(file)]
                output = output + self.runCmd(cmd, workdir)
        
        return output

    def _gitCommit(self, workdir, msg, description=None, authorname=None, authoremail=None):
        output = ''

        cmd = ['git', 'commit', '-m',  quote(msg)]
        if description:
            cmd.extend(['-m ', quote(description.replace("\n", "\\n"))])
        
        if authorname:
            authorargstr = quote(authorname) 
            if  authoremail:
                authorargstr = quote(authorname + " <" + authoremail + ">")

            authorarg = '--author=' + authorargstr
            cmd.append(authorarg)
        
        output = output + self.runCmd(cmd, workdir)

        return output

    def getGitInitCmds(self, initgit_dir):
        indir = quote(initgit_dir)
        if self.isWindows():
            indir = initgit_dir.replace('\\', '\\\\')

        initcmd = ['git', 'init ', indir]
        if self.isWindows():
            initcmd = ['cd', indir, '&&', 'git', 'init'] # hotfix, fallback command of git init ... is not working, I don't know why @FIXME
        
        return [
            initcmd,
            ['git', 'lfs', 'install'],
            ['git', 'lfs', 'track', '"*.kra"'],
            ['git', 'lfs', 'track', '"*.png"'],
            ['git', 'lfs', 'track', '"_preview.png"']
        ]

    def runGitInit(self, initgit_dir):
        output = ''
        cmds = self.getGitInitCmds(initgit_dir)
        for cmd in cmds:
            output = output + self.runCmd(cmd, initgit_dir)

        src_gitignore_file = os.path.join(self.script_abs_path, ".gitignore")
        dest_gitignore_file = os.path.join(initgit_dir, ".gitignore")
        try:
            if not os.path.exists(dest_gitignore_file):
                shutil.copyfile(src_gitignore_file, dest_gitignore_file)
        except IOError as e:
            output = output + "Unable to copy file: {} {}".format(dest_gitignore_file, e)

        gitattributes_file = os.path.join(initgit_dir, ".gitattributes")

        cmds = [
            ['git', 'add ', quote(dest_gitignore_file)],
            ['git', 'add ', quote(gitattributes_file)],
            ['git', 'commit', '-m', quote('update gitignore and gitattributes')]
        ]

        for cmd in cmds:
            output = output + self.runCmd(cmd, initgit_dir)

        return output

    def generateDocumentMetaFiles(self):
        files = self._generateDocumentFiles(True)
        output = "generate Files: " + "\n - ".join(str(x) for x in files) + "\n\n"
        return output

    def generateDocument(self):
        files = self._generateDocumentFiles(False)
        output = "generate Files: " + "\n - ".join(str(x) for x in files) + "\n\n"
        return output

    def _generateDocumentFiles(self, onlymetafiles=False):
        if self.durradocument.hasKritaDocument():
            filename = self.durradocument.getFilenameKra()

            if filename:
                files = []
                if onlymetafiles:
                    files = self.makeMetaFiles()
                else:
                    files = self.makeFiles()

                return files
            else:
                self.println('filename is empty')
        else:
            self.println('document is not set')

        return []



    def commitDocumentMetafiles(self, extramsg=None):
        return self._commitDocument(True, extramsg)
    
    def commitDocument(self, extramsg=None):
        return self._commitDocument(False, extramsg)

    def _commitDocument(self, onlymetafiles=False, extramsg=None):
        if self.durradocument.hasKritaDocument():
            filename = self.durradocument.getFilenameKra()

            if filename != "":
                files = self._generateDocumentFiles(onlymetafiles)

                name = self.durradocument.getKritaDocument().name()
                workdir_basename = os.path.basename(os.path.normpath(self.workdir))

                outputfiles = "generate Files: " + "\n - ".join(str(x) for x in files) + "\n\n"

                nr = ""
                mnrs = re.search(r"^\s*(\d+)\s+\-\s+.*$", workdir_basename)
                nr = mnrs.group(1) if mnrs is not None else ""
                nrstr = None
                close_issue_msg = ""
                if nr:
                    nrstr = "#{0}".format(int(nr))
                    close_issue_msg = " Closes " + nrstr

                msg = ""

                if self.durradocument.releaseversion:
                    if self.durradocument.versionstr == "1.0.0":
                        msg = "finished " + name + " v" + self.durradocument.versionstr + close_issue_msg
                    else:
                        msg = "new version of " + name + " v" + self.durradocument.versionstr
                else:
                    msg = "work on "
                    if nrstr is not None:
                        msg = msg + nrstr + " "
                    msg = msg + name

                output = self.runGit(self.workdir, files, msg, extramsg, self.durradocument.authorname, self.durradocument.authoremail)

                return outputfiles + output
            else:
                return 'filename is empty'
        else:
            return 'document is not set'


    def newMajorVersion(self):
        return self.durradocument.setNewMajorVersion()

    def newMinjorVersion(self):
        return self.durradocument.setNewMinjorVersion()

    def newPatchVersion(self):
        return self.durradocument.setNewPatchVersion()

    def newPatchedVersion(self):
        return self.newPatchVersion()

    def revisionVersion(self):
        return self.durradocument.setRevisionVersion()




    
    def generateDocumentMetafilesCurrentVersion(self):
        if self.durradocument.hasKritaDocument():
            return self.generateDocumentMetaFiles()
        else:
            return 'document is not set'
    
    def commitDocumentMetafilesCurrentVersion(self, extramsg=None):
        if self.durradocument.hasKritaDocument():
            return self.commitDocumentMetafiles(extramsg)
        else:
            return 'document is not set'

    
    def generateDocumentCurrentVersion(self):
        if self.durradocument.hasKritaDocument():
            if not self.durradocument.releaseversion:
                self.revisionVersion()
            return self.generateDocument()
        else:
            return 'document is not set'

    def commitDocumentCurrentVersion(self, extramsg=None):
        if self.durradocument.hasKritaDocument():
            if not self.durradocument.releaseversion:
                self.revisionVersion()
            return self.commitDocument(extramsg)
        else:
            return 'document is not set'



    def generateDocumentNewMinjorVersion(self):
        if self.durradocument.hasKritaDocument():
            self.newMinjorVersion()
            return self.generateDocument()
        else:
            return 'document is not set'

    def commitDocumentNewMinjorVersion(self, extramsg=None):
        if self.durradocument.hasKritaDocument():
            self.newMinjorVersion()
            return self.commitDocument(extramsg)
        else:
            return 'document is not set'



    def generateDocumentNewMajorVersion(self):
        if self.durradocument.hasKritaDocument():
            self.newMajorVersion()
            return self.generateDocument()
        else:
            return 'document is not set'

    def commitDocumentNewMajorVersion(self, extramsg=None):
        if self.durradocument.hasKritaDocument():
            self.newMajorVersion()
            return self.commitDocument(extramsg)
        else:
            return 'document is not set'



    def generateDocumentNewPatchedVersion(self):
        if self.durradocument.hasKritaDocument():
            self.newPatchedVersion()
            return self.generateDocument()
        else:
            return 'document is not set'

    def commitDocumentNewPatchedVersion(self, extramsg=None):
        if self.durradocument.hasKritaDocument():
            self.newPatchedVersion()
            return self.commitDocument(extramsg)
        else:
            return 'document is not set'

