# Copyright 2013 Mike Wakerly <opensource@hoho.com>
#
# This file is part of the Pykeg package of the Kegbot project.
# For more information on Pykeg or Kegbot, see http://kegbot.org/
#
# Pykeg is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# Pykeg is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Pykeg.  If not, see <http://www.gnu.org/licenses/>.

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.shortcuts import redirect
from socialregistration.clients.oauth import OAuthError
from socialregistration.contrib.foursquare.client import Foursquare
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render_to_response
from django.template import RequestContext
import oauth2 as oauth

import foursquare

from . import forms

class FoursquareClient(Foursquare):
    def set_callback_url(self, url):
        self.callback_url = url

    def get_callback_url(self):
        return self.callback_url


@staff_member_required
def admin_settings(request, plugin):
    context = RequestContext(request)
    settings_form = plugin.get_site_settings_form()

    if request.method == 'POST':
        if 'submit-settings' in request.POST:
            settings_form = forms.SiteSettingsForm(request.POST)
            if settings_form.is_valid():
                client_id = settings_form.cleaned_data['client_id']
                client_secret = settings_form.cleaned_data['client_secret']
                venue_id = settings_form.cleaned_data['venue_id']
                client = foursquare.Foursquare(client_id=client_id, client_secret=client_secret)
                venue = None
                try:
                    # Search for the venue. Simultaneous validates all three credentials.
                    if venue_id:
                        venue = client.venues(venue_id)
                except foursquare.FoursquareException, e:
                    messages.error(request, 'Error testing Foursquare connection: %s' % str(e))
                else:
                    plugin.save_site_settings_form(settings_form)
                    plugin.save_venue_detail(venue)
                    messages.success(request, 'Settings updated')

    context['plugin'] = plugin
    context['settings_form'] = settings_form
    context['venue_detail'] = plugin.get_venue_detail()

    return render_to_response('contrib/foursquare/foursquare_admin_settings.html', context_instance=context)


@login_required
def user_settings(request, plugin):
    context = RequestContext(request)
    user = request.user

    settings_form = plugin.get_user_settings_form(user)

    if request.method == 'POST':
        if 'submit-settings' in request.POST:
            settings_form = forms.UserSettingsForm(request.POST)
            if settings_form.is_valid():
                plugin.save_user_settings_form(user, settings_form)
                messages.success(request, 'Settings updated')

    context['plugin'] = plugin
    context['venue'] = plugin.get_venue_detail()
    context['profile'] = plugin.get_user_profile(user)
    context['settings_form'] = settings_form

    return render_to_response('contrib/foursquare/foursquare_user_settings.html', context_instance=context)


@staff_member_required
def auth_redirect(request):
    if 'submit-remove' in request.POST:
        plugin = request.plugins.get('foursquare')
        plugin.save_user_profile(request.user, None)
        plugin.save_user_token(request.user, '')
        messages.success(request, 'Removed Foursquare account.')
        return redirect('account-plugin-settings', plugin_name='foursquare')

    plugin = request.plugins['foursquare']
    client = get_client(*plugin.get_credentials())

    url = request.kbsite.settings.reverse_full('plugin-foursquare-callback')
    client.set_callback_url(url)

    request.session['foursquare_client'] = client

    try:
        return redirect(client.get_redirect_url())
    except OAuthError, error:
        messages.error(request, 'Error: %s' % str(error))
        return redirect('account-plugin-settings', plugin_name='foursquare')


@staff_member_required
def auth_callback(request):
    try:
        client = request.session['foursquare_client']
        del request.session['foursquare_client']
        token = client.complete(dict(request.GET.items()))
    except KeyError:
        messages.error(request, 'Session expired.')
    except OAuthError, error:
        messages.error(request, str(error))
    else:
        plugin = request.plugins.get('foursquare')
        profile = client.get_user_info()
        token = client.get_access_token()
        plugin.save_user_profile(request.user, profile)
        plugin.save_user_token(request.user, token)

        username = '%s %s' % (profile.get('firstName'), profile.get('lastName'))
        messages.success(request, 'Successfully linked to foursquare user %s' % username)

    return redirect('account-plugin-settings', plugin_name='foursquare')


def get_client(client_id, client_secret):
    client = FoursquareClient()
    client.client_id = client_id
    client.secret = client_secret
    return client
