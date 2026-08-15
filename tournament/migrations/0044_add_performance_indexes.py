from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tournament', '0043_league_description'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='matchprediction',
            unique_together={('match', 'player')},
        ),
        migrations.AddIndex(
            model_name='leaguemember',
            index=models.Index(fields=['league', 'player', 'is_verified'], name='tour_lm_l_p_v_idx'),
        ),
        migrations.AddIndex(
            model_name='match',
            index=models.Index(fields=['tournament', 'date_time'], name='tour_match_t_dt_idx'),
        ),
        migrations.AddIndex(
            model_name='match',
            index=models.Index(fields=['tournament', 'is_finished'], name='tour_match_t_fin_idx'),
        ),
        migrations.AddIndex(
            model_name='match',
            index=models.Index(fields=['tournament', 'group'], name='tour_match_t_grp_idx'),
        ),
        migrations.AddIndex(
            model_name='match',
            index=models.Index(fields=['tournament', 'stage'], name='tour_match_t_stg_idx'),
        ),
        migrations.AddIndex(
            model_name='matchprediction',
            index=models.Index(fields=['match', 'player'], name='tour_mp_m_p_idx'),
        ),
        migrations.AddIndex(
            model_name='matchprediction',
            index=models.Index(fields=['player'], name='tour_mp_p_idx'),
        ),
        migrations.AddIndex(
            model_name='sidebet',
            index=models.Index(fields=['tournament'], name='tour_sb_t_idx'),
        ),
        migrations.AddIndex(
            model_name='sidebetanswer',
            index=models.Index(fields=['sidebet', 'player'], name='tour_sba_sb_p_idx'),
        ),
        migrations.AddIndex(
            model_name='sidebetanswer',
            index=models.Index(fields=['player'], name='tour_sba_p_idx'),
        ),
        migrations.AddIndex(
            model_name='tournamentsubmission',
            index=models.Index(fields=['tournament', 'player'], name='tour_ts_t_p_idx'),
        ),
        migrations.AddIndex(
            model_name='tournamentsubmission',
            index=models.Index(fields=['player'], name='tour_ts_p_idx'),
        ),
    ]
