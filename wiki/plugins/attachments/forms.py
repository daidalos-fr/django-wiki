# -*- coding: utf-8 -*-
from django import forms
from django.utils.translation import ugettext as _

from wiki.plugins.attachments import models
from wiki.core.permissions import can_moderate

import zipfile
from django.core.files.uploadedfile import File
import tempfile
from wiki.plugins.attachments.models import IllegalFileExtension

class AttachmentForm(forms.ModelForm):
    
    description = forms.CharField(
        label=_(u'Description'),
        help_text=_(u'A short summary of what the file contains'),
        required=False
    )
    
    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file', None)
        if uploaded_file:
            try:
                models.extension_allowed(uploaded_file.name)
            except IllegalFileExtension, e:
                raise forms.ValidationError(e)
        return uploaded_file

    def __init__(self, *args, **kwargs):
        self.article = kwargs.pop('article', None)
        self.request = kwargs.pop('request', None)
        super(AttachmentForm, self).__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        attachment_revision = super(AttachmentForm, self).save(commit=False)
        
        # Added because of AttachmentArcihveForm removing file from fields
        # should be more elegant
        attachment_revision.file = self.cleaned_data['file']
        
        attachment = models.Attachment()
        attachment.article = self.article
        attachment.original_filename = attachment_revision.get_filename()
        attachment.save()
        attachment.articles.add(self.article)
        attachment_revision.attachment = attachment
        attachment_revision.set_from_request(self.request)
        attachment_revision.save()
        return attachment_revision
    
    class Meta:
        model = models.AttachmentRevision
        fields = ('file', 'description',)

class AttachmentArcihveForm(AttachmentForm):
    
    file = forms.FileField( #@ReservedAssignment
        label=_(u'File or zip archive'),
        required=True
    )
    
    unzip_archive = forms.BooleanField(
        label=_(u'Unzip file'),
        help_text=_(u'Create individual attachments for files in a .zip file - directories do not work.'),
        required=False
    )
    
    def __init__(self, *args, **kwargs):
        super(AttachmentArcihveForm, self).__init__(*args, **kwargs)
        ordered_fields = ['unzip_archive', 'file']
        self.fields.keyOrder = ordered_fields + [k for k in self.fields.keys() if k not in ordered_fields]
        
    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file', None)
        if uploaded_file and self.cleaned_data.get('unzip_archive', False):
            try:
                self.zipfile = zipfile.ZipFile(uploaded_file.file, mode="r")
                for zipinfo in self.zipfile.filelist:
                    try:
                        models.extension_allowed(zipinfo.filename)
                    except IllegalFileExtension, e:
                        raise forms.ValidationError(e)
            except zipfile.BadZipfile:
                raise forms.ValidationError(_(u"Not a zip file"))
        else:
            return super(AttachmentArcihveForm, self).clean_file()
        return uploaded_file
    
    def clean(self):
        if not can_moderate(self.article, self.request.user):
            raise forms.ValidationError("User")
        return self.cleaned_data
        
    def save(self, *args, **kwargs):
        
        # This is not having the intended effect
        if not 'file' in self._meta.fields:
            self._meta.fields.append('file')
        
        if self.cleaned_data['unzip_archive']:
            new_attachments = []
            try:
                for zipinfo in self.zipfile.filelist:
                    f = tempfile.NamedTemporaryFile(mode='r+w')
                    f.write(self.zipfile.read(zipinfo.filename))
                    f = File(f, name=zipinfo.filename)
                    try:
                        attachment = models.Attachment()
                        attachment.article = self.article
                        attachment.original_filename = zipinfo.filename
                        attachment.save()
                        attachment.articles.add(self.article)
                        attachment_revision = models.AttachmentRevision()
                        attachment_revision.file = f
                        attachment_revision.description = self.cleaned_data['description']
                        attachment_revision.attachment = attachment
                        attachment_revision.set_from_request(self.request)
                        attachment_revision.save()
                        f.close()
                    except models.IllegalFileExtension:
                        raise
                    new_attachments.append(attachment_revision)
            except zipfile.BadZipfile:
                raise
            return new_attachments
        else:
            return super(AttachmentArcihveForm, self).save(*args, **kwargs)

    class Meta(AttachmentForm.Meta):
        fields = ['description',]

class DeleteForm(forms.Form):
    """This form is both used for dereferencing and deleting attachments"""
    confirm = forms.BooleanField(label=_(u'Yes I am sure...'),
                                 required=False)
    
    def clean_confirm(self):
        if not self.cleaned_data['confirm']:
            raise forms.ValidationError(_(u'You are not sure enough!'))
        return True

class SearchForm(forms.Form):
    
    query = forms.CharField(label="", widget=forms.TextInput(attrs={'class': 'search-query'}),)
