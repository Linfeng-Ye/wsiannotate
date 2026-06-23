from django import forms


class BulkUserCreationForm(forms.Form):
    usernames = forms.CharField(
        widget=forms.Textarea,
        help_text='Enter one username per line',
        required=False,
    )
    number_of_users = forms.IntegerField(
        min_value=1,
        required=False,
        label='Number of users to generate',
        help_text=(
            'Generate this many users automatically '
            '(e.g. user1, user2, ...)'
        ),
    )
