from rest_framework import serializers


class ReportFilterSerializer(serializers.Serializer):
    session = serializers.IntegerField(required=False, min_value=1)
    term = serializers.IntegerField(required=False, min_value=1)
    class_level = serializers.IntegerField(required=False, min_value=1)
    arm = serializers.IntegerField(required=False, min_value=1)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    view = serializers.ChoiceField(choices=("summary", "students"), required=False, default="summary")
    search = serializers.CharField(required=False, allow_blank=True, max_length=100)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)
    export = serializers.ChoiceField(choices=("csv",), required=False)

    def validate(self, attrs):
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        if start and end and start > end:
            raise serializers.ValidationError({"start_date": "Start date must be on or before end date."})
        return attrs
