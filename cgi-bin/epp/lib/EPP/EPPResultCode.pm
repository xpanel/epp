package EPP::EPPResultCode;

###############################################################################
#
#	-------------------------
#			XPanel EPP Server
#		-------------------------
#
#	Version: 1.0.0
#	Web Site: http://www.xpanel.com/
#
#	(c) Copyright 2017 XPanel Ltd.
#
# *  XPanel Ltd. licenses this file to You under the Apache License, Version 2.0
# *  (the "License"); you may not use this file except in compliance with
# *  the License.  You may obtain a copy of the License at
# *
# *      http://www.apache.org/licenses/LICENSE-2.0
# *
# *  Unless required by applicable law or agreed to in writing, software
# *  distributed under the License is distributed on an "AS IS" BASIS,
# *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#
###############################################################################



use strict;
use warnings;

use EPP::EPPResultCode ":all";

our %_totext;
our @_langs;

BEGIN {
	use Exporter ();
	our ($VERSION, @ISA, @EXPORT, @EXPORT_OK, %EXPORT_TAGS);

	$VERSION = do { my @r = (q$Revision: 1.01 $ =~ /\d+/g); sprintf "%d."."%02d" x $#r, @r};
	@ISA = qw(Exporter);
	@EXPORT = qw(epp_result_totext epp_languages epp_success);
	@EXPORT_OK = qw(epp_result_totext epp_languages epp_success);
	%EXPORT_TAGS = (all => \@EXPORT_OK);

	my %langhash;

	sub _d {
		my ($numeric, $code, $text) = @_;

		eval "sub ${code}() { $numeric; }";
		foreach my $lang (keys %{$text}) {
			$_totext{$numeric}->{$lang} = $text->{$lang};
			$langhash{$lang} = 1;
		}
		push(@EXPORT, $code);
		push(@EXPORT_OK, $code);
	}

	_d(1000, 'EPP_RS_SUCCESS', {
		'en-US' => 'Command completed successfully',
		'fr-FR' => "la commande terminée avec succès" });

	_d(1001, 'EPP_RS_PENDING', {
		'en-US' => 'Command completed successfully; action pending',
		'fr-FR' => "la commande terminée avec succès ; l;'action est en suspens" });

	_d(1300, 'EPP_RS_NOMSG', {
		'en-US' => 'Command completed successfully; no messages',
		'fr-FR' => "la commande terminée avec succès ; il n'ya acun message" });

	_d(1301, 'EPP_RS_ACK', {
		'en-US' => 'Command completed successfully; ack to dequeue',
		'fr-FR' => "la commande terminé avec succès ; ack à retirer de la file d'attente" });

	_d(1500, 'EPP_RS_END', {
		'en-US' => 'Command completed successfully; ending session',
		'fr-FR' => "la commande terminé avec succès ; la session termine" });

	_d(2000, 'EPP_RF_UNKCMD', {
		'en-US' => 'Unknown command',
		'fr-FR' => "la commande est inconnue" });

	_d(2001, 'EPP_RF_SYNTAX', {
		'en-US' => 'Command syntax error',
		'fr-FR' => "erreur de syntaxe à la commande" });

	_d(2002, 'EPP_RF_CMDUSE', {
		'en-US' => 'Command use error',
		'fr-FR' => "erreur d'utilisation à la commande" });

	_d(2003, 'EPP_RF_PARAM', {
		'en-US' => 'Required parameter missing',
		'fr-FR' => "paramètre exigé est manquant" });

	_d(2004, 'EPP_RF_VALRANGE', {
		'en-US' => 'Parameter value range error',
		'fr-FR' => "la valeur de paramètre est hors d'intervalle" });

	_d(2005, 'EPP_RF_VALSYNTAX', {
		'en-US' => 'Parameter value syntax error',
		'fr-FR' => "erreur de syntaxe en valeur de paramètre" });

	_d(2100, 'EPP_RF_PROTVERS', {
		'en-US' => 'Unimplemented protocol version',
		'fr-FR' => "la version de protocole n'est pas mise en application" });

	_d(2101, 'EPP_RF_UNIMPCMD', {
		'en-US' => 'Unimplemented command',
		'fr-FR' => "la commande n'est pas mise en application" });

	_d(2102, 'EPP_RF_UNIMPOPT', {
		'en-US' => 'Unimplemented option',
		'fr-FR' => "l'option n'est pas mise en application" });

	_d(2103, 'EPP_RF_UNIMPEXT', {
		'en-US' => 'Unimplemented extension',
		'fr-FR' => "l'extension n'est pas mise en application" });

	_d(2104, 'EPP_RF_BILLING', {
		'en-US' => 'Billing failure',
		'fr-FR' => "panne de facturation" });

	_d(2105, 'EPP_RF_NORENEW', {
		'en-US' => 'Object is not eligible for renewal',
		'fr-FR' => "l'objet n'est pas habilité au renouvellement" });

	_d(2106, 'EPP_RF_NOTRANSFER', {
		'en-US' => 'Object is not eligible for transfer',
		'fr-FR' => "l'objet n'est pas éligible pour être transféré" });

	_d(2200, 'EPP_RF_AUTHENTICATION', {
		'en-US' => 'Authentication error',
		'fr-FR' => "erreur d'authentification" });

	_d(2201, 'EPP_RF_AUTHORIZATION', {
		'en-US' => 'Authorization error',
		'fr-FR' => "erreur d'autorisation" });

	_d(2202, 'EPP_RF_INVAUTHOR', {
		'en-US' => 'Invalid authorization information',
		'fr-FR' => "l'information d'autorisation est incorrecte" });

	_d(2300, 'EPP_RF_PENDINGTRANSFER', {
		'en-US' => 'Object pending transfer',
		'fr-FR' => "l'objet est transfert en suspens" });

	_d(2301, 'EPP_RF_NOTPENDINGTRANSFER', {
		'en-US' => 'Object not pending transfer',
		'fr-FR' => "l'objet n'est pas transfert en suspens" });

	_d(2302, 'EPP_RF_EXISTS', {
		'en-US' => 'Object exists',
		'fr-FR' => "l'objet existe" });

	_d(2303, 'EPP_RF_NOTEXISTS', {
		'en-US' => 'Object does not exist',
		'fr-FR' => "l'objet n'existe pas" });

	_d(2304, 'EPP_RF_STATUS', {
		'en-US' => 'Object status prohibits operation',
		'fr-FR' => "le statut de l'objet interdit cette exécution" });

	_d(2305, 'EPP_RF_INUSE', {
		'en-US' => 'Object association prohibits operation',
		'fr-FR' => "l'assocation de l'objet interdit cette exécution" });

	_d(2306, 'EPP_RF_POLICYPARAM', {
		'en-US' => 'Parameter value policy error',
		'fr-FR' => "erreur de politique en valeur du paramètre" });

	_d(2307, 'EPP_RF_UNIMPLSERVICE', {
		'en-US' => 'Unimplemented object service',
		'fr-FR' => "le service d'objet n'est pas mis en application" });

	_d(2308, 'EPP_RF_DATAMGT', {
		'en-US' => 'Data management policy violation',
		'fr-FR' => "violation de la politique de gestion des données" });

	_d(2400, 'EPP_RF_FAIL', {
		'en-US' => 'Command failed',
		'fr-FR' => "la commande a échoué" });

	_d(2500, 'EPP_RF_CLOSING', {
		'en-US' => 'Command failed; server closing connection',
		'fr-FR' => "la commande a échoué ; le serveur ferme la connexion" });

	_d(2501, 'EPP_RF_AUTHCLOSING', {
		'en-US' => 'Authentiction error; server closing connection',
		'fr-FR' => "erreur d'authentification ; le serveur ferme la connexion" });

	_d(2502, 'EPP_RF_SESSIONLIMIT', {
		'en-US' => 'Session limit exceeded; server closing connection',
		'fr-FR' => "la limite de session a été dépassée ; le serveur ferme la connexion" });

	@_langs = keys %langhash;
	}

	our @EXPORT_OK;

sub epp_result_totext {
	my ($res, $lang) = @_;

	if (defined($lang) && defined($_totext{$res}->{$lang})) {
		return $_totext{$res}->{$lang};
	}
	else {
		return $_totext{$res}->{'en-US'};
	}
}

sub epp_languages {
	return @_langs;
}

sub epp_success {
	my ($code) = @_;

	return (($code >= 1000) && ($code < 2000));
}

1;